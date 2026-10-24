
import os
import sys

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# These are the 8 rules from the current ClaimLoom seed data.
RULES_DATA = [
    {
        "rule_id": 1,
        "violation_type": "Brand Naming",
        "severity": "Medium",
        "rule_cited": "Use the official brand name consistently.",
        "source_ref": "team_provided_brand_brief",
        "rule_text": "Always write the brand name as ClaimLoom.",
        "regex_pattern": r"\bclaimloom\b|\bCLAIMLOOM\b",
        "default_fix": "Replace the incorrect spelling with ClaimLoom.",
        "claim_status": "approved",
    },
    {
        "rule_id": 2,
        "violation_type": "Product Claim",
        "severity": "High",
        "rule_cited": "Product performance claims must match approved specifications.",
        "source_ref": "team_provided_product_brief",
        "rule_text": "The certified battery range is 110 km.",
        "regex_pattern": None,
        "default_fix": "Use the approved battery range wording and verify the specification.",
        "claim_status": "approved",
    },
    {
        "rule_id": 3,
        "violation_type": "Terminology",
        "severity": "Medium",
        "rule_cited": "Use the terminology specified in the brand brief.",
        "source_ref": "team_provided_brand_brief",
        "rule_text": 'Refer to users as "Creators" or "Team Members", not "clients" or "consumers".',
        "regex_pattern": r"\b(clients|consumers)\b",
        "default_fix": 'Replace "clients" or "consumers" with the appropriate approved term.',
        "claim_status": "approved",
    },
    {
        "rule_id": 4,
        "violation_type": "Tone",
        "severity": "Medium",
        "rule_cited": "Communications should maintain the approved brand tone.",
        "source_ref": "team_provided_brand_brief",
        "rule_text": "Maintain a professional, clear, and non-aggressive tone.",
        "regex_pattern": None,
        "default_fix": "Rewrite the wording in a professional, clear, and respectful tone.",
        "claim_status": "approved",
    },
    {
        "rule_id": 5,
        "violation_type": "Pricing Claim",
        "severity": "High",
        "rule_cited": "Pricing must match the approved product brief.",
        "source_ref": "team_provided_product_brief",
        "rule_text": "The Pro Plan costs $29 per month or $290 per year.",
        "regex_pattern": None,
        "default_fix": "Correct the price to match the approved pricing information.",
        "claim_status": "approved",
    },
    {
        "rule_id": 6,
        "violation_type": "Accessibility",
        "severity": "Medium",
        "rule_cited": "Instructions should not rely on color or screen position alone.",
        "source_ref": "team_provided_brand_brief",
        "rule_text": 'Avoid directions such as "click the green button on the right".',
        "regex_pattern": None,
        "default_fix": "Identify the control by its label or accessible name.",
        "claim_status": "approved",
    },
    {
        "rule_id": 7,
        "violation_type": "Unsupported Guarantee",
        "severity": "High",
        "rule_cited": "Avoid absolute guarantees and unsupported zero-risk claims.",
        "source_ref": "team_provided_brand_brief",
        "rule_text": "Do not make absolute guarantees or claim that a product or process has zero risk.",
        "regex_pattern": r"\b(zero risk|100% guaranteed|guaranteed results)\b",
        "default_fix": "Replace absolute wording with a specific, evidence-supported statement.",
        "claim_status": "approved",
    },
    {
        "rule_id": 8,
        "violation_type": "Product Claim",
        "severity": "High",
        "rule_cited": "Charging claims must match approved specifications.",
        "source_ref": "team_provided_product_brief",
        "rule_text": "The approved charging claim is 0% to 80% in 45 minutes.",
        "regex_pattern": None,
        "default_fix": "Use the approved charging time and verify the product specification.",
        "claim_status": "approved",
    },
]

# These are the 5 facts from the current ClaimLoom seed data.
FACTS_DATA = [
    {
        "fact_id": 101,
        "fact_text": "The certified battery range is 110 km.",
        "source_ref": "team_provided_product_brief",
    },
    {
        "fact_id": 102,
        "fact_text": "The approved charging claim is 0% to 80% in 45 minutes.",
        "source_ref": "team_provided_product_brief",
    },
    {
        "fact_id": 103,
        "fact_text": "The Pro Plan costs $29 per month or $290 per year.",
        "source_ref": "team_provided_product_brief",
    },
    {
        "fact_id": 104,
        "fact_text": "The stated warranty is 3 years or 30,000 km.",
        "source_ref": "team_provided_product_brief",
    },
    {
        "fact_id": 105,
        "fact_text": "The stated brand colors are #1E3A8A and #FF5500.",
        "source_ref": "team_provided_brand_brief",
    },
]


def migrate_brand_rules(cur):
    """
    Preserve the existing brand_rules table and its embedding column.
    Migrate the old id/category columns if they still exist.
    """
    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.brand_rules (
            rule_id SERIAL PRIMARY KEY,
            violation_type VARCHAR(100) NOT NULL,
            severity VARCHAR(20),
            rule_cited TEXT,
            source_ref TEXT,
            rule_text TEXT NOT NULL,
            regex_pattern TEXT,
            default_fix TEXT,
            claim_status VARCHAR(50),
            embedding VECTOR(768)
        );
    """)

    cur.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'brand_rules';
    """)
    columns = {row[0] for row in cur.fetchall()}

    # Support the old schema: id, category, rule_text, embedding.
    if "id" in columns and "rule_id" not in columns:
        cur.execute("""
            ALTER TABLE public.brand_rules
            RENAME COLUMN id TO rule_id;
        """)
        columns.remove("id")
        columns.add("rule_id")

    if "category" in columns and "violation_type" not in columns:
        cur.execute("""
            ALTER TABLE public.brand_rules
            RENAME COLUMN category TO violation_type;
        """)
        columns.remove("category")
        columns.add("violation_type")

    # Add missing fields without dropping existing data.
    missing_columns = {
        "severity": "VARCHAR(20)",
        "rule_cited": "TEXT",
        "source_ref": "TEXT",
        "regex_pattern": "TEXT",
        "default_fix": "TEXT",
        "claim_status": "VARCHAR(50)",
        "embedding": "VECTOR(768)",
    }

    for column, sql_type in missing_columns.items():
        if column not in columns:
            cur.execute(
                f"ALTER TABLE public.brand_rules "
                f"ADD COLUMN {column} {sql_type};"
            )

    # The old category field may have been required and may now be renamed.
    # Make the migrated table compatible with the new rule data.
    cur.execute("""
        ALTER TABLE public.brand_rules
        ALTER COLUMN violation_type TYPE VARCHAR(100);
    """)


def create_other_tables(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.facts (
            fact_id INT PRIMARY KEY,
            fact_text TEXT NOT NULL,
            source_ref TEXT
        );

        CREATE TABLE IF NOT EXISTS public.scans (
            scan_id VARCHAR(50) PRIMARY KEY,
            readiness_score INT,
            status VARCHAR(30),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS public.flag_events (
            event_id SERIAL PRIMARY KEY,
            scan_id VARCHAR(50),
            rule_id INT,
            action VARCHAR(20)
                CHECK (action IN ('Accepted', 'Dismissed', 'Overridden')),
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_flag_events_scan_id
            ON public.flag_events(scan_id);

        CREATE INDEX IF NOT EXISTS idx_flag_events_rule_id
            ON public.flag_events(rule_id);
    """)


def seed_rules(cur):
    query = """
        INSERT INTO public.brand_rules (
            rule_id,
            violation_type,
            severity,
            rule_cited,
            source_ref,
            rule_text,
            regex_pattern,
            default_fix,
            claim_status
        )
        VALUES (
            %(rule_id)s,
            %(violation_type)s,
            %(severity)s,
            %(rule_cited)s,
            %(source_ref)s,
            %(rule_text)s,
            %(regex_pattern)s,
            %(default_fix)s,
            %(claim_status)s
        )
        ON CONFLICT (rule_id) DO UPDATE SET
            violation_type = EXCLUDED.violation_type,
            severity = EXCLUDED.severity,
            rule_cited = EXCLUDED.rule_cited,
            source_ref = EXCLUDED.source_ref,
            rule_text = EXCLUDED.rule_text,
            regex_pattern = EXCLUDED.regex_pattern,
            default_fix = EXCLUDED.default_fix,
            claim_status = EXCLUDED.claim_status;
    """

    for rule in RULES_DATA:
        cur.execute(query, rule)

    # Explicit IDs do not automatically advance a SERIAL sequence.
    cur.execute("""
        SELECT setval(
            pg_get_serial_sequence('public.brand_rules', 'rule_id'),
            GREATEST(COALESCE(MAX(rule_id), 1), 1),
            COUNT(*) > 0
        )
        FROM public.brand_rules;
    """)


def seed_facts(cur):
    query = """
        INSERT INTO public.facts (fact_id, fact_text, source_ref)
        VALUES (%(fact_id)s, %(fact_text)s, %(source_ref)s)
        ON CONFLICT (fact_id) DO UPDATE SET
            fact_text = EXCLUDED.fact_text,
            source_ref = EXCLUDED.source_ref;
    """

    for fact in FACTS_DATA:
        cur.execute(query, fact)


def seed_demo_events_if_empty(cur):
    """
    Insert example audit events only when flag_events is empty.
    These are demo records, not real user actions.
    """
    cur.execute("SELECT COUNT(*) FROM public.flag_events;")
    event_count = cur.fetchone()[0]

    if event_count != 0:
        print("Existing flag_events found; demo events were not inserted.")
        return

    demo_events = [
        ("scan_demo1", 1, "Accepted", "Demo: brand name corrected."),
        ("scan_demo2", 2, "Dismissed", "Demo: claim needs human review."),
        ("scan_demo3", 3, "Overridden", "Demo: terminology exception."),
        ("scan_demo4", 5, "Accepted", "Demo: pricing wording reviewed."),
        ("scan_demo5", 7, "Dismissed", "Demo: absolute claim flagged."),
    ]

    cur.executemany("""
        INSERT INTO public.flag_events (scan_id, rule_id, action, reason)
        VALUES (%s, %s, %s, %s);
    """, demo_events)

    print("Inserted 5 demo flag events.")


def seed_neon_database():
    if not DATABASE_URL or "ep-xyz" in DATABASE_URL:
        print(
            "ERROR: A real DATABASE_URL was not found. "
            "Check your .env file. Database was not seeded."
        )
        sys.exit(1)

    connection = None

    try:
        print("Connecting to Neon...")

        connection = psycopg2.connect(DATABASE_URL)

        with connection.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

            migrate_brand_rules(cur)
            create_other_tables(cur)

            seed_rules(cur)
            seed_facts(cur)
            seed_demo_events_if_empty(cur)

        connection.commit()

        print("Neon Database successfully seeded with brand_rules, facts, scans, and flag_events!")

    except Exception as error:
        if connection is not None:
            connection.rollback()

        print("Database seeding failed.")
        print(f"Error: {error}")
        sys.exit(1)

    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    seed_neon_database()
