import os
import re
from rank_bm25 import BM25Okapi
from google import genai
from google.genai import types
from db import get_db_connection

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def get_kb_version(workspace_id: str = "default") -> int:
    """Returns the max version of the KB for cache invalidation."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COALESCE(MAX(version_no), 1) FROM public.kb_sources WHERE workspace_id = %s;", (workspace_id,))
            return cur.fetchone()[0]
    finally:
        conn.close()

def reaudit_changed_chunks(chunk_ids: list[int]) -> list[str]:
    """Flags past approved scans for re-audit if their source facts change."""
    if not chunk_ids:
        return []
    conn = get_db_connection()
    affected_scans = []
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT scan_id FROM public.claim_evidence WHERE chunk_id = ANY(%s);", (chunk_ids,))
            affected_scans = [row[0] for row in cur.fetchall()]
            
            if affected_scans:
                cur.execute("UPDATE public.scan_documents SET reaudit_needed = TRUE WHERE scan_id = ANY(%s);", (affected_scans,))
        conn.commit()
    finally:
        conn.close()
    return affected_scans

def record_evidence(scan_id: str, chunk_ids: list[int]) -> None:
    """Links a scan to the KB chunks it relied on for future re-audits."""
    if not chunk_ids:
        return
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            for cid in chunk_ids:
                cur.execute("""
                    INSERT INTO public.claim_evidence (scan_id, chunk_id, verdict, similarity)
                    VALUES (%s, %s, 'Linked', 1.0)
                """, (scan_id, cid))
        conn.commit()
    finally:
        conn.close()

def extract_numbers_with_units(text: str) -> set:
    """Extracts pairs like '110 km', '$29', '45 minutes', '2 years'."""
    pattern = r'(\$?\d+(?:\.\d+)?)\s*(km|minutes|months|years|/month|/year|%|)'
    matches = re.findall(pattern, text.lower())
    return {f"{num}{unit}" for num, unit in matches}

def verify_claims(text: str, workspace_id: str = "default") -> dict:
    """
    Hybrid pgvector + BM25 RAG Pipeline.
    Returns: {"verified_claims": [...], "contradicted_issues": [...]}
    """
    response = client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config=types.EmbedContentConfig(output_dimensionality=768, task_type="RETRIEVAL_QUERY")
    )
    draft_embedding = response.embeddings[0].values

    conn = get_db_connection()
    verified_claims = []
    contradicted_issues = []
    
    try:
        with conn.cursor() as cur:
            # Fetch dense (pgvector) matches
            cur.execute("""
                SELECT c.chunk_id, c.chunk_text, c.page_num, s.doc_title, 
                       (1 - (c.embedding <=> %s::vector)) AS sim 
                FROM public.kb_chunks c
                JOIN public.kb_sources s ON c.source_id = s.source_id
                WHERE c.workspace_id = %s
                ORDER BY c.embedding <=> %s::vector LIMIT 10;
            """, (draft_embedding, workspace_id, draft_embedding))
            
            db_chunks = cur.fetchall()
            if not db_chunks:
                return {"verified_claims": [], "contradicted_issues": []}

            # Run sparse (BM25) on the retrieved corpus
            corpus = [row[1].lower().split() for row in db_chunks]
            bm25 = BM25Okapi(corpus)
            query_tokens = text.lower().split()
            bm25_scores = bm25.get_scores(query_tokens)

            # Apply Reciprocal Rank Fusion (RRF)
            fused_results = []
            for idx, row in enumerate(db_chunks):
                chunk_id, chunk_text, page_num, doc_title, dense_sim = row
                
                dense_rank = idx + 1
                bm25_rank = sorted(range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True).index(idx) + 1
                
                rrf_score = (1 / (60 + dense_rank)) + (1 / (60 + bm25_rank))
                fused_results.append({
                    "chunk_id": chunk_id, "excerpt": chunk_text, 
                    "page": page_num, "doc_title": doc_title, 
                    "similarity": dense_sim, "rrf": rrf_score
                })

            fused_results.sort(key=lambda x: x["rrf"], reverse=True)
            top_chunk = fused_results[0]
            
            # Deterministic Math Verification
            draft_nums = extract_numbers_with_units(text)
            kb_nums = extract_numbers_with_units(top_chunk["excerpt"])
            matches = draft_nums.intersection(kb_nums)

            evidence_obj = {
                "doc_title": top_chunk["doc_title"],
                "page": top_chunk["page"],
                "paragraph": 1,
                "excerpt": top_chunk["excerpt"],
                "similarity": round(top_chunk["similarity"], 2),
                "chunk_id": top_chunk["chunk_id"]
            }

            if top_chunk["similarity"] >= 0.72 and matches:
                evidence_obj["verdict"] = "Verified"
                verified_claims.append(evidence_obj)
            
            elif top_chunk["similarity"] >= 0.70 and draft_nums and not matches:
                evidence_obj["verdict"] = "Contradicted"
                contradicted_issues.append({
                    "id": f"rag_{top_chunk['chunk_id']}",
                    "severity": "High",
                    "claim_status": "Contradicted Fact",
                    "violation_type": "Factual",
                    "flagged_text": list(draft_nums)[0] if draft_nums else "Quantitative claim",
                    "rule_cited": "Truth Vault KB Contradiction",
                    "source_ref": f"{top_chunk['doc_title']}, p.{top_chunk['page']}",
                    "explanation": "Contradicts verified product specs in the Knowledge Base.",
                    "suggested_fix": list(kb_nums)[0] if kb_nums else "Check KB",
                    "confidence": 0.95,
                    "detected_by": "rag_verifier",
                    "evidence": evidence_obj
                })

    finally:
        conn.close()

    return {
        "verified_claims": verified_claims,
        "contradicted_issues": contradicted_issues
    }