import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
from db import get_db_connection
load_dotenv()
# The official Truth Vault documents for Round 3
KB_DOCS = [
    {
        "doc_title": "Product_Spec_Sheet_2026.md",
        "source_type": "product_spec",
        "chunks": [
            "Maximum certified battery range is 110 km per charge under standard testing conditions.",
            "Fast charging enables 0 to 80% battery capacity in 45 minutes."
        ]
    },
    {
        "doc_title": "Approved_Pricing_Policy.md",
        "source_type": "pricing",
        "chunks": [
            "The ClaimLoom Pro Plan subscription costs $29/month billed monthly, or $290/year."
        ]
    },
    {
        "doc_title": "Legal_Warranty_Terms.md",
        "source_type": "legal",
        "chunks": [
            "All enterprise hardware comes with a 2-year limited hardware warranty.",
            "Enterprise software agreements include a 99.9% uptime SLA."
        ]
    },
    {
        "doc_title": "Visual_Accessibility_Standard.md",
        "source_type": "brand_guidelines",
        "chunks": [
            "Approved primary brand hex palette: #1E3A8A (Blue), #FF5722 (Orange), and #FFFFFF (White)."
        ]
    }
]

def seed_truth_vault():
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    conn = get_db_connection()

    try:
        with conn.cursor() as cur:
            # Clear any existing KB data to prevent duplicates on rerun
            cur.execute("TRUNCATE TABLE public.kb_sources CASCADE;")

            for doc in KB_DOCS:
                # 1. Insert Source Document
                cur.execute("""
                    INSERT INTO public.kb_sources (workspace_id, doc_title, source_type)
                    VALUES ('default', %s, %s) RETURNING source_id;
                """, (doc["doc_title"], doc["source_type"]))
                source_id = cur.fetchone()[0]

                # 2. Embed and Insert Chunks
                for idx, chunk_text in enumerate(doc["chunks"]):
                    print(f"Embedding chunk {idx+1} for {doc['doc_title']}...")
                    
                    response = client.models.embed_content(
                        model="gemini-embedding-001",
                        contents=chunk_text,
                        config=types.EmbedContentConfig(
                            output_dimensionality=768,
                            task_type="RETRIEVAL_DOCUMENT"
                        )
                    )
                    embedding = response.embeddings[0].values

                    cur.execute("""
                        INSERT INTO public.kb_chunks (source_id, workspace_id, page_num, chunk_text, embedding)
                        VALUES (%s, 'default', 1, %s, %s::vector);
                    """, (source_id, chunk_text, embedding))
        
        conn.commit()
        print("Successfully seeded the Truth Vault Knowledge Base with pgvector embeddings!")
        
    except Exception as e:
        conn.rollback()
        print(f"Error seeding KB: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    seed_truth_vault()