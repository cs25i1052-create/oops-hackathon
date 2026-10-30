"""AI client that survives free-tier problems.

Idea: never depend on ONE model. Several providers (all speak the same OpenAI-style API) are tried
in order. If a model was retired (404), rate limited (429), has a bad key (401) or times out,
it is skipped for a while and the next one is tried. If everything fails, AIUnavailable is raised and
the app still returns the rule-engine results, marked ai_status="degraded".

Add or change providers/models with environment variables only, no code edits:
  GROQ_MODELS=openai/gpt-oss-120b,qwen/qwen3.6-27b      (comma list, tried in order)
  GEMINI_MODELS=gemini-3.5-flash,gemini-3.1-flash-lite
  OPENROUTER_MODELS=openrouter/free
  CUSTOM_BASE_URL / CUSTOM_API_KEY / CUSTOM_MODELS       (any other OpenAI-compatible service)
  AI_PROVIDER_ORDER=groq,gemini,openrouter,custom
"""
import base64
import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

PROVIDERS = [
    {"name": "groq", "base_url": "https://api.groq.com/openai/v1", "key_env": "GROQ_API_KEY",
     "models_env": "GROQ_MODELS", "default_models": "openai/gpt-oss-120b,qwen/qwen3.6-27b,openai/gpt-oss-20b",
     "vision_env": None, "default_vision": ""},
    {"name": "gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "key_env": "GEMINI_API_KEY",
     "models_env": "GEMINI_MODELS", "default_models": "gemini-3.5-flash,gemini-3.1-flash-lite",
     "vision_env": "GEMINI_VISION_MODELS", "default_vision": "gemini-3.5-flash"},
    {"name": "openrouter", "base_url": "https://openrouter.ai/api/v1", "key_env": "OPENROUTER_API_KEY",
     "models_env": "OPENROUTER_MODELS", "default_models": "openrouter/free",
     "vision_env": "OPENROUTER_VISION_MODELS", "default_vision": "openrouter/free"},
    {"name": "custom", "base_url": "", "base_url_env": "CUSTOM_BASE_URL", "key_env": "CUSTOM_API_KEY",
     "models_env": "CUSTOM_MODELS", "default_models": "",
     "vision_env": "CUSTOM_VISION_MODELS", "default_vision": ""},
]

PER_CALL_TIMEOUT = float(os.getenv("AI_CALL_TIMEOUT", "12.0"))
TOTAL_BUDGET = float(os.getenv("AI_TOTAL_TIMEOUT", "30"))
NUDGE = "\n\nIMPORTANT: your previous reply was not valid JSON. Reply with ONE valid JSON object only. No markdown, no commentary."

# model names that are never chat models (used only by auto-discovery)
_GOOD = re.compile(r"(gpt-oss|llama|qwen|gemini|mistral|deepseek|gemma)", re.I)
_BAD = re.compile(r"(whisper|tts|guard|embed|image|audio|live|moderation|safeguard|orpheus|robotics|imagen|veo|omni)", re.I)

_cooldown: Dict[Tuple[str, str], float] = {}
_successful_model_by_provider: Dict[str, str] = {}
_successful_provider: Optional[str] = None


class AIUnavailable(Exception):
    """Every configured provider/model failed."""


# ----------------------------------------------------------------- tiny HTTP wrappers (tests replace these)
_http_client = httpx.Client(
    timeout=PER_CALL_TIMEOUT,
    limits=httpx.Limits(max_keepalive_connections=10, max_connections=20, keepalive_expiry=60.0),
)


def _post(url: str, headers: dict, payload: dict, timeout: float) -> Tuple[int, str]:
    r = _http_client.post(url, headers=headers, json=payload, timeout=timeout)
    return r.status_code, r.text


def _get(url: str, headers: dict, timeout: float) -> Tuple[int, str]:
    r = _http_client.get(url, headers=headers, timeout=timeout)
    return r.status_code, r.text


# ----------------------------------------------------------------- configuration
def _clean(value: Optional[str]) -> str:
    return (value or "").strip().strip('"').strip("'")


def _configured(p: dict, vision: bool = False) -> Optional[dict]:
    key = _clean(os.getenv(p["key_env"]))
    if not key or "your_" in key.lower():
        return None
    base = _clean(os.getenv(p["base_url_env"])) if p.get("base_url_env") else p["base_url"]
    if not base:
        return None
    if vision:
        if not p.get("vision_env"):
            return None
        raw = os.getenv(p["vision_env"], p["default_vision"])
    else:
        raw = os.getenv(p["models_env"], p["default_models"])
    models = [m.strip() for m in raw.split(",") if m.strip()]
    if not models:
        return None
    return {**p, "key": key, "base_url": base.rstrip("/"), "models": models}


def _ordered_providers(vision: bool = False) -> List[dict]:
    order = [x.strip() for x in os.getenv("AI_PROVIDER_ORDER", "groq,gemini,openrouter,custom").split(",") if x.strip()]
    by_name = {p["name"]: p for p in PROVIDERS}
    result = []
    for name in order:
        if name in by_name:
            cfg = _configured(by_name[name], vision)
            if cfg:
                successful_model = _successful_model_by_provider.get(name) if not vision else None
                if successful_model and successful_model in cfg["models"]:
                    cfg["models"] = [successful_model] + [m for m in cfg["models"] if m != successful_model]
                result.append(cfg)
    if not vision and _successful_provider:
        result.sort(key=lambda provider: provider["name"] != _successful_provider)
    return result


def has_any_provider() -> bool:
    return bool(_ordered_providers())


def _on_cooldown(provider: str, model: str) -> bool:
    now = time.monotonic()
    return _cooldown.get((provider, model), 0) > now or _cooldown.get((provider, "*"), 0) > now


def _set_cooldown(provider: str, model: str, seconds: float) -> None:
    _cooldown[(provider, model)] = time.monotonic() + seconds


def reset_cooldowns() -> None:
    _cooldown.clear()


# ----------------------------------------------------------------- one HTTP call
def _extract_json(text: str) -> Any:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    text = re.sub(r"```(?:json)?", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise


def _call_model(p: dict, model: str, system: str, user: str, image: Optional[Tuple[bytes, str]],
                max_tokens: int, timeout: float, json_mode: bool = True, temperature: float = 0.0):
    """Returns (content_text, None) on success or (None, (kind, message)) on failure.
    kind: 'auth' | 'missing' | 'rate' | 'error'"""
    if image:
        b64 = base64.b64encode(image[0]).decode()
        user_content: Any = [
            {"type": "text", "text": user},
            {"type": "image_url", "image_url": {"url": f"data:{image[1]};base64,{b64}"}},
        ]
    else:
        user_content = user
    payload = {
        "model": model.replace("models/", ""),
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user_content}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {p['key']}", "Content-Type": "application/json"}
    try:
        status, body = _post(p["base_url"] + "/chat/completions", headers, payload, timeout)
    except Exception as e:  # timeouts, DNS, connection resets
        return None, ("error", f"{type(e).__name__}")
    if status == 200:
        try:
            content = json.loads(body)["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
            if not content or not str(content).strip():
                return None, ("error", "empty reply")
            return str(content), None
        except Exception:
            return None, ("error", "unreadable response")
    if status == 400 and json_mode:  # this model may not support JSON mode -> retry without it
        return _call_model(p, model, system, user, image, max_tokens, timeout, json_mode=False, temperature=temperature)
    snippet = body[:160].replace("\n", " ")
    if status in (401, 403):
        return None, ("auth", f"HTTP {status} (check the API key)")
    if status == 404:
        return None, ("missing", f"HTTP 404 (model retired or renamed)")
    if status == 429:
        return None, ("rate", "HTTP 429 (rate limited)")
    return None, ("error", f"HTTP {status} {snippet}")


def _apply_cooldown(p: dict, model: str, kind: str) -> None:
    if kind == "auth":
        _set_cooldown(p["name"], "*", 600)
    elif kind == "missing":
        _set_cooldown(p["name"], model, 3600)
    elif kind == "rate":
        _set_cooldown(p["name"], model, 60)
    else:
        _set_cooldown(p["name"], model, 30)


def _attempt(p: dict, model: str, system: str, user: str, image, max_tokens: int, deadline: float, errors: List[str]):
    """One model, with one JSON-repair retry. Returns (parsed_json | None, kind)."""
    for attempt in range(2):
        call_limit = max(PER_CALL_TIMEOUT, 12.0) if image is not None else PER_CALL_TIMEOUT
        timeout = min(call_limit, deadline - time.monotonic())
        if timeout < 1:
            errors.append("time budget used up")
            return None, "timeout"
        content, fail = _call_model(p, model, system if attempt == 0 else system + NUDGE, user, image,
                                    max_tokens, timeout, temperature=0.0 if attempt == 0 else 0.3)
        if fail:
            kind, msg = fail
            errors.append(f"{p['name']}/{model}: {msg}")
            _apply_cooldown(p, model, kind)
            return None, kind
        try:
            data = _extract_json(content)
            if isinstance(data, (dict, list)):
                return data, "ok"
        except Exception:
            pass
        errors.append(f"{p['name']}/{model}: reply was not valid JSON")
    _set_cooldown(p["name"], model, 30)
    return None, "parse"


def _discover_models(p: dict, vision: bool) -> List[str]:
    """Last resort when every configured model is gone: ask the provider what it offers now."""
    try:
        status, body = _get(p["base_url"] + "/models", {"Authorization": f"Bearer {p['key']}"}, 10)
        if status != 200:
            return []
        items = json.loads(body).get("data", [])
        ids = [str(i.get("id", "")).replace("models/", "") for i in items]
        picks = [i for i in ids if i and _GOOD.search(i) and not _BAD.search(i)]
        if vision:
            picks = [i for i in picks if re.search(r"(gemini|vision|vl)", i, re.I)]
        return picks[:2]
    except Exception:
        return []


# ----------------------------------------------------------------- public API
def complete_json(system: str, user: str, image: Optional[Tuple[bytes, str]] = None,
                  max_tokens: int = 3000) -> Tuple[Any, str]:
    """Returns (parsed_json, 'provider/model'). Raises AIUnavailable if nothing works."""
    deadline = time.monotonic() + TOTAL_BUDGET
    providers = _ordered_providers(vision=image is not None)
    if not providers:
        raise AIUnavailable("no AI API key configured")
    errors: List[str] = []
    global _successful_provider
    for p in providers:
        if _on_cooldown(p["name"], "*"):
            errors.append(f"{p['name']}: skipped (cooling down)")
            continue
        candidates = [m for m in p["models"] if not _on_cooldown(p["name"], m)]
        missing = 0
        for model in candidates:
            if time.monotonic() >= deadline:
                raise AIUnavailable("; ".join(errors[-6:]) or "time budget used up")
            data, kind = _attempt(p, model, system, user, image, max_tokens, deadline, errors)
            if kind == "ok":
                _successful_model_by_provider[p["name"]] = model
                if image is None:
                    _successful_provider = p["name"]
                return data, f"{p['name']}/{model}"
            if kind == "auth":
                break  # bad key: no point trying this provider's other models
            if kind == "missing":
                missing += 1
        if candidates and missing == len(candidates) and not _on_cooldown(p["name"], "*"):
            for model in _discover_models(p, vision=image is not None):
                data, kind = _attempt(p, model, system, user, image, max_tokens, deadline, errors)
                if kind == "ok":
                    return data, f"{p['name']}/{model} (auto-discovered)"
    raise AIUnavailable("; ".join(errors[-6:]) or "all providers failed")


def status() -> List[dict]:
    """Live diagnostic for /api/ai-status: tests each provider with a tiny request."""
    report = []
    for p in PROVIDERS:
        cfg = _configured(p)
        if not cfg:
            report.append({"provider": p["name"], "configured": False})
            continue
        entry = {"provider": p["name"], "configured": True, "working_model": None, "failures": []}
        for model in cfg["models"]:
            content, fail = _call_model(cfg, model, "Reply with JSON only.", 'Return exactly: {"ok": true}', None, 200, 15)
            if not fail:
                entry["working_model"] = model
                break
            entry["failures"].append({"model": model, "problem": fail[1]})
        report.append(entry)
    return report
