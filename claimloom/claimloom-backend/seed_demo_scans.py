import json
from db import get_db_connection

def seed_demo_scans():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # 1. Prepare two dummy pre-approved scans
            demo_scans = [
                ("demo_scan_1", "Our new Pro Plan is amazing at just $29/month!"),
                ("demo_scan_2", "Sign up today for $29/month to get the Pro Plan features.")
            ]
            
            for scan_id, text in demo_scans:
                mock_result = {
                    "scan_id": scan_id,
                    "status": "approved",
                    "readiness_score": 100,
                    "issues": []
                }
                
                # Insert into scan_documents
                cur.execute("""
                    INSERT INTO public.scan_documents 
                        (scan_id, workspace_id, channel, redacted_text, result_json, reaudit_needed)
                    VALUES (%s, 'default', 'general', %s, %s::jsonb, FALSE)
                    ON CONFLICT (scan_id) DO NOTHING;
                """, (scan_id, text, json.dumps(mock_result)))

                # 2. Link them to the Pricing chunk (chunk_id = 3) in claim_evidence
                # This ensures that when the judge changes the price to $39, these get flagged!
                cur.execute("""
                    INSERT INTO public.claim_evidence (scan_id, chunk_id, verdict, similarity)
                    VALUES (%s, 3, 'Verified', 0.95);
                """, (scan_id,))
        
        conn.commit()
        print("Successfully seeded the Demo Scans for the Live Price Change feature!")
    except Exception as e:
        conn.rollback()
        print(f"Error seeding demo scans: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    seed_demo_scans()