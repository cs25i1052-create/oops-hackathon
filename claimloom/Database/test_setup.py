
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

database_url = os.getenv("DATABASE_URL")

if not database_url:
    raise ValueError("DATABASE_URL is missing from .env")

print("Connecting to Neon...")

try:
    conn = psycopg2.connect(database_url)

    with conn.cursor() as cur:
        cur.execute("""
            SELECT current_database(), current_user;
        """)
        database, user = cur.fetchone()

        cur.execute("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = 'brand_rules';
        """)
        table_exists = cur.fetchone()[0] == 1

    print("Connected successfully!")
    print("Database:", database)
    print("Database role:", user)
    print("brand_rules table exists:", table_exists)

    conn.close()

except Exception as error:
    print("Connection failed:", error)
    raise
