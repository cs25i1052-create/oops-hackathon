"""Tier 1 (no AI): PII redaction, the regex rule engine, channel-specific governance rules,
no-op fix filtering, and highlight-position helpers."""
import re
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from schemas import WEIGHTS, IssueItem, normalize_channel

# ---------------------------------------------------------------- PII redaction
# Every match is replaced by the SAME number of "X" so start/end positions never shift.
PII_PATTERNS = [
    r"[A-Za-z0-9_.+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]+",                              # emails
    r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)",                                              # card-like numbers
    r"(?<!\w)\+\d{1,3}[\s.-]?\d{2,5}[\s.-]?\d{3,5}(?:[\s.-]?\d{2,5})?(?!\d)",       # +CC phone numbers
    r"(?<!\d)[6-9]\d{4}[\s-]?\d{5}(?!\d)",                                           # Indian 10-digit mobiles
]

# Channel-specific deterministic rules (applies when channel != "general")
CHANNEL_REGEX_RULES: Dict[str, List[Dict]] = {
    "linkedin": [
        {
            "rule_id": 1001,
            "violation_type": "Tone",
            "severity": "Low",
            "rule_cited": "Channel Rule (LinkedIn): Professional CTA Standard",
            "source_ref": "Channel Playbook 2026 — LinkedIn B2B Voice",
            "rule_text": "Avoid casual social slang ('DM me', 'link in bio', 'smash that like') on LinkedIn.",
            "regex_pattern": r"(?i)\b(?:dm\s+me|link\s+in\s+bio|smash\s+that\s+like(?:\s+button)?|drop\s+a\s+fire\s+emoji)\b",
            "default_fix": "connect with our team",
        },
    ],
    "instagram": [
        {
            "rule_id": 1002,
            "violation_type": "Accessibility",
            "severity": "Low",
            "rule_cited": "Channel Rule (Instagram): Non-Clickable URL in Caption",
            "source_ref": "Channel Playbook 2026 — Instagram Formatting",
            "rule_text": "Raw URLs in Instagram captions are not clickable. Direct Creators to the link in bio instead.",
            "regex_pattern": r"https?://[^\s)>\]]+",
            "default_fix": "the link in our bio",
        },
    ],
    "billboard": [
        {
            "rule_id": 1003,
            "violation_type": "Accessibility",
            "severity": "Medium",
            "rule_cited": "Channel Rule (Billboard): No Web URLs or Click Prompts on OOH Assets",
            "source_ref": "Channel Playbook 2026 — Out-of-Home (Billboard) Safety",
            "rule_text": "Motorists cannot click links or type long URLs while driving. Use a short brand name search prompt instead.",
            "regex_pattern": r"(?i)(?:https?://[^\s)>\]]+|www\.[^\s)>\]]+|\b(?:click|tap)\s+(?:here|now|below)\b)",
            "default_fix": "Search ClaimLoom",
        },
    ],
    "email": [
        {
            "rule_id": 1004,
            "violation_type": "Tone",
            "severity": "Medium",
            "rule_cited": "Channel Rule (Email): Deliverability & Spam-Trigger Filter",
            "source_ref": "Channel Playbook 2026 — Email Compliance",
            "rule_text": "Avoid high-pressure spam trigger phrases ('Act now', '100% free', 'Urgent action required', 'Click below immediately') that route emails to spam folders.",
            "regex_pattern": r"(?i)\b(?:act\s+now|urgent\s+action\s+required|100%\s+free|free\s+money|no\s+obligation|click\s+below\s+immediately|once\s+in\s+a\s+lifetime)\b",
            "default_fix": "explore the details",
        },
        {
            "rule_id": 1005,
            "violation_type": "Tone",
            "severity": "Low",
            "rule_cited": "Channel Rule (Email): No ALL-CAPS Shouting Phrases",
            "source_ref": "Channel Playbook 2026 — Email Compliance",
            "rule_text": "Avoid 3+ consecutive ALL-CAPS words in marketing emails, which trigger spam filters and hurt readability.",
            "regex_pattern": r"\b[A-Z]{4,}(?:\s+[A-Z]{3,}){2,}\b",
            "default_fix": None,  # dynamically title/sentence-cased in _pick_fix
        },
    ],
}


def redact_pii_same_length(text: str) -> Tuple[str, int]:
    count = 0

    def mask(match):
        nonlocal count
        count += 1
        return "X" * len(match.group(0))

    for pattern in PII_PATTERNS:
        text = re.sub(pattern, mask, text)
    return text, count


# ---------------------------------------------------------------- helpers
@lru_cache(maxsize=256)
def compile_pattern(pattern: str):
    return re.compile(pattern)


def is_noop_fix(flagged_text: str, suggested_fix: str) -> bool:
    """Returns True if the suggested fix is empty or identical to the flagged text
    (prevents the 'ClaimLoom' -> 'ClaimLoom' self-flagging bug)."""
    f_clean = (flagged_text or "").strip()
    s_clean = (suggested_fix or "").strip()
    if not f_clean or not s_clean:
        return True
    return f_clean == s_clean


def to_utf16(text: str, index: int) -> int:
    """Python counts emoji as 1 character, JavaScript counts them as 2. Convert so highlights match."""
    if index is None or index < 0:
        return -1
    return len(text[:index].encode("utf-16-le")) // 2


def overlaps(a_start: int, a_end: int, spans: List[Tuple[int, int]]) -> bool:
    if a_start < 0 or a_end < 0:
        return False
    return any(s >= 0 and e >= 0 and a_start < e and a_end > s for s, e in spans)


def locate_phrase(draft: str, phrase: str, taken: List[Tuple[int, int]]) -> Tuple[int, int]:
    """Finds `phrase` in the ORIGINAL draft. Ignores case/extra spaces, and skips
    occurrences that are already flagged, so repeated phrases each get their own highlight."""
    words = (phrase or "").split()
    if not words:
        return -1, -1
    pattern = r"\s+".join(map(re.escape, words))
    for m in re.finditer(pattern, draft, re.IGNORECASE):
        if not overlaps(m.start(), m.end(), taken):
            return m.start(), m.end()
    return -1, -1


def _pick_fix(rule: Dict, matched: str) -> str:
    fix = rule.get("default_fix")
    if not fix:
        # Fallback for ALL-CAPS shouting rule -> convert to capitalized sentence case
        if matched.isupper() and len(matched) > 3:
            return matched.capitalize()
        return matched
    if "|" in fix:  # "Creator|Creators" -> singular|plural
        singular, plural = fix.split("|", 1)
        fix = plural if matched.lower().endswith("s") else singular
    return fix


def _allowed_numbers(rule: Dict) -> set:
    raw = rule.get("allowed_numbers")
    if not raw:
        return set()
    return {float(x) for x in str(raw).split(",") if x.strip()}


# ---------------------------------------------------------------- Channel structural checks
def run_channel_rules(text: str, channel: str = "general") -> List[IssueItem]:
    """Runs deterministic channel-specific rules for linkedin, instagram, billboard, and email."""
    ch = normalize_channel(channel)
    if ch == "general":
        return []

    found: List[IssueItem] = []

    # 1. Regex-based channel rules
    for rule in CHANNEL_REGEX_RULES.get(ch, []):
        rx = compile_pattern(rule["regex_pattern"])
        for m in rx.finditer(text):
            start, end = m.span()
            matched = text[start:end]
            fix = _pick_fix(rule, matched)
            if is_noop_fix(matched, fix):
                continue
            found.append(
                IssueItem(
                    id="",
                    severity=rule["severity"],
                    violation_type=rule["violation_type"],
                    flagged_text=matched,
                    start=start,
                    end=end,
                    rule_id=rule["rule_id"],
                    rule_cited=rule["rule_cited"],
                    source_ref=rule["source_ref"],
                    explanation=f"Violates {rule['rule_cited']}. {rule['rule_text']}",
                    suggested_fix=fix,
                    confidence=1.0,
                    detected_by="rule_engine",
                    claim_status=None,
                    channel=ch,
                )
            )

    # 2. Structural channel checks (Billboard word cap & LinkedIn hashtag cap)
    if ch == "billboard":
        word_matches = list(re.finditer(r"\S+", text))
        if len(word_matches) > 12:
            # Flag the overflow span starting from word 13 to the end of the text
            overflow_start = word_matches[12].start()
            overflow_end = word_matches[-1].end()
            flagged_overflow = text[overflow_start:overflow_end]
            concise_fix = " ".join(m.group(0) for m in word_matches[:10]).rstrip(".,;:") + "."
            if not is_noop_fix(flagged_overflow, concise_fix):
                found.append(
                    IssueItem(
                        id="",
                        severity="Medium",
                        violation_type="Accessibility",
                        flagged_text=flagged_overflow,
                        start=overflow_start,
                        end=overflow_end,
                        rule_id=1006,
                        rule_cited="Channel Rule (Billboard): Maximum 12-Word Readability Limit",
                        source_ref="Channel Playbook 2026 — Out-of-Home (Billboard) Legibility",
                        explanation=(
                            f"Billboard copy has {len(word_matches)} words (limit is 12 words for 3-second highway legibility). "
                            "Trim the trailing copy so motorists can read it at a glance."
                        ),
                        suggested_fix="[Remove excess words to stay under 12 words]",
                        confidence=1.0,
                        detected_by="rule_engine",
                        claim_status=None,
                        channel=ch,
                    )
                )

    elif ch == "linkedin":
        hashtags = list(re.finditer(r"(?<!\w)#[A-Za-z0-9_]+", text))
        if len(hashtags) > 5:
            overflow_start = hashtags[5].start()
            overflow_end = hashtags[-1].end()
            flagged_tags = text[overflow_start:overflow_end]
            keep_three = " ".join(h.group(0) for h in hashtags[:3])
            if not is_noop_fix(flagged_tags, keep_three):
                found.append(
                    IssueItem(
                        id="",
                        severity="Low",
                        violation_type="Tone",
                        flagged_text=flagged_tags,
                        start=overflow_start,
                        end=overflow_end,
                        rule_id=1007,
                        rule_cited="Channel Rule (LinkedIn): Maximum 5 Hashtags",
                        source_ref="Channel Playbook 2026 — LinkedIn B2B Voice",
                        explanation=(
                            f"Post contains {len(hashtags)} hashtags (maximum 5 allowed on LinkedIn). "
                            "Excess hashtags reduce feed distribution and look spammy."
                        ),
                        suggested_fix=keep_three,
                        confidence=1.0,
                        detected_by="rule_engine",
                        claim_status=None,
                        channel=ch,
                    )
                )

        # LinkedIn copy should avoid shouty capitalization and stacked punctuation.
        for match in re.finditer(r"!{2,}", text):
            flagged = match.group(0)
            if not is_noop_fix(flagged, "!"):
                found.append(IssueItem(
                    id="", severity="Low", violation_type="Tone", flagged_text=flagged,
                    start=match.start(), end=match.end(), rule_id=1008,
                    rule_cited="Channel Rule (LinkedIn): Professional Punctuation",
                    source_ref="Channel Playbook 2026 — LinkedIn B2B Voice",
                    explanation="Use at most one exclamation mark in professional LinkedIn copy.",
                    suggested_fix="!", confidence=1.0, detected_by="rule_engine", channel=ch,
                ))
        for match in re.finditer(r"\b[A-Z]{6,}\b", text):
            flagged = match.group(0)
            fix = flagged.capitalize()
            if not is_noop_fix(flagged, fix):
                found.append(IssueItem(
                    id="", severity="Low", violation_type="Tone", flagged_text=flagged,
                    start=match.start(), end=match.end(), rule_id=1009,
                    rule_cited="Channel Rule (LinkedIn): Avoid All-Caps Copy",
                    source_ref="Channel Playbook 2026 — LinkedIn B2B Voice",
                    explanation="Avoid all-caps words longer than five letters; they read as shouting in professional posts.",
                    suggested_fix=fix, confidence=1.0, detected_by="rule_engine", channel=ch,
                ))

    elif ch == "instagram":
        words = list(re.finditer(r"\S+", text))
        if len(words) > 150 and "\n" not in text:
            flagged = text.strip()
            if flagged and not is_noop_fix(flagged, "Break copy into shorter paragraphs"):
                found.append(IssueItem(
                    id="", severity="Low", violation_type="Accessibility", flagged_text=flagged,
                    start=-1, end=-1, rule_id=1010,
                    rule_cited="Channel Rule (Instagram): Caption Readability",
                    source_ref="Channel Playbook 2026 — Instagram Formatting",
                    explanation=f"This {len(words)}-word caption has no line breaks. Split long copy into short, scannable paragraphs.",
                    suggested_fix="Break copy into shorter paragraphs", confidence=1.0,
                    detected_by="rule_engine", channel=ch,
                ))

    return found


# ---------------------------------------------------------------- Tier 1 engine
def run_rule_engine(
    text: str,
    rules: List[Dict],
    scope: str = "text",
    channel: str = "general",
) -> List[IssueItem]:
    """Exact regex checks + channel rules. Zero hallucination, exact positions.
    Drops any candidate where flagged_text.strip() == suggested_fix.strip()."""
    ch = normalize_channel(channel)
    found: List[IssueItem] = []

    for rule in rules:
        if rule.get("applies_to", "text") not in (scope, "both"):
            continue
        # If a database rule specifies a channel column, honor it
        rule_channel = normalize_channel(rule.get("channel")) if rule.get("channel") else "general"
        if rule_channel != "general" and rule_channel != ch:
            continue

        pattern = rule.get("regex_pattern")
        if not pattern:
            continue
        try:
            rx = compile_pattern(pattern)
        except re.error:
            continue  # a bad pattern typed into the database must never crash a scan
        allowed = _allowed_numbers(rule)
        rule_id = int(rule.get("rule_id") or -1)
        matches = re.finditer(r"(?i)\b\d+(?:,\d{3})?\s*km\b", text) if rule_id == 2 else rx.finditer(text)
        for m in matches:
            # Battery range claims need range context. A speed such as 150 km/h
            # or a location 200 km away is not a product-range claim.
            if rule_id == 2:
                value_match = re.search(r"\d+(?:,\d{3})?", m.group(0))
                if not value_match or float(value_match.group(0).replace(",", "")) <= 110:
                    continue
                suffix = re.match(r"\s+range\b", text[m.end():], re.IGNORECASE)
                prefix = re.search(r"\brange\s+(?:(?:is|of)\s+)?$", text[max(0, m.start() - 24):m.start()], re.IGNORECASE)
                if suffix:
                    claim_start, claim_end = m.start(), m.end() + suffix.end()
                elif prefix:
                    claim_start = max(0, m.start() - 24) + prefix.start()
                    claim_end = m.end()
                else:
                    continue
            else:
                claim_start, claim_end = m.start(), m.end()
            if allowed and "num" in rx.groupindex and m.group("num"):
                try:
                    if float(m.group("num")) in allowed:
                        continue  # price/number is approved, no violation
                except ValueError:
                    pass
            if rule_id == 2:
                start, end = claim_start, claim_end
            elif "flag" in rx.groupindex and m.group("flag"):
                start, end = m.span("flag")
            else:
                start, end = m.span()
            matched = text[start:end]
            fix = _pick_fix(rule, matched)

            # Fix-First Guard: drop self-identical flags (e.g., "ClaimLoom" -> "ClaimLoom")
            if is_noop_fix(matched, fix):
                continue

            found.append(
                IssueItem(
                    id="",
                    severity=rule["severity"],
                    violation_type=rule["violation_type"],
                    flagged_text=matched,
                    start=start,
                    end=end,
                    rule_id=rule["rule_id"],
                    rule_cited=rule["rule_cited"],
                    source_ref=rule["source_ref"],
                    explanation=f"Violates {rule['rule_cited']}. {rule['rule_text']}",
                    suggested_fix=fix,
                    confidence=1.0,
                    detected_by="rule_engine",
                    claim_status=rule.get("claim_status"),
                    channel=ch,
                )
            )

    if scope in ("text", "both"):
        found.extend(run_channel_rules(text, channel=ch))

    return _drop_overlaps(found)


def _drop_overlaps(issues: List[IssueItem]) -> List[IssueItem]:
    """If two rules flag the same words, keep the more severe one."""
    issues.sort(key=lambda i: (i.start if i.start is not None else -1, -WEIGHTS.get(i.severity, 12)))
    kept: List[IssueItem] = []
    for iss in issues:
        s = iss.start if iss.start is not None else -1
        e = iss.end if iss.end is not None else -1
        if not overlaps(s, e, [(k.start or -1, k.end or -1) for k in kept]):
            kept.append(iss)
    return kept
