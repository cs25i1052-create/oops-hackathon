"""Seed searchable Truth Vault chunks without deleting evidence history."""
import hashlib

from seed_db import FACTS_DATA

KB_CHUNKS = [
    {"chunk_id": i, "doc_title": fact["source_ref"].split(", p.")[0], "page_num": int(fact["source_ref"].rsplit("p.", 1)[-1]) if "p." in fact["source_ref"] else 1, "paragraph_num": 1, "chunk_text": fact["fact_text"]}
    for i, fact in enumerate(FACTS_DATA, 1)
]


def seed_kb(conn):
    with conn.cursor() as cur:
        cur.execute("CREATE TABLE IF NOT EXISTS public.kb_chunks (chunk_id INT PRIMARY KEY, doc_title TEXT NOT NULL, page_num INT NOT NULL DEFAULT 1, paragraph_num INT NOT NULL DEFAULT 1, chunk_text TEXT NOT NULL, content_hash TEXT, embedding JSONB, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);")
        cur.execute("CREATE TABLE IF NOT EXISTS public.kb_meta (key TEXT PRIMARY KEY, value INT NOT NULL DEFAULT 1);")
        cur.execute("INSERT INTO public.kb_meta (key, value) VALUES ('kb_version', 1) ON CONFLICT (key) DO NOTHING;")
        for chunk in KB_CHUNKS:
            digest = hashlib.sha256(chunk["chunk_text"].encode()).hexdigest()
            cur.execute("""INSERT INTO public.kb_chunks (chunk_id, doc_title, page_num, paragraph_num, chunk_text, content_hash) VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (chunk_id) DO UPDATE SET doc_title=EXCLUDED.doc_title,page_num=EXCLUDED.page_num,paragraph_num=EXCLUDED.paragraph_num,chunk_text=EXCLUDED.chunk_text,content_hash=EXCLUDED.content_hash,updated_at=CURRENT_TIMESTAMP;""", (chunk["chunk_id"], chunk["doc_title"], chunk["page_num"], chunk["paragraph_num"], chunk["chunk_text"], digest))
