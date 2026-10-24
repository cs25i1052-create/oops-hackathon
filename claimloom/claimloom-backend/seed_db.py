"""Brand Truth Vault data + script that loads it into Neon.
Run once (and again whenever you edit a rule):   python seed_db.py
The app reads rules from Neon; if Neon is unreachable it falls back to the lists below."""
import os

from dotenv import load_dotenv

load_dotenv()

# Pattern tips (see engine.py):
#   (?P<flag>...)  highlight only that part      (?P<num>...) + allowed_numbers -> flag numbers not on the list
#   default_fix "A|B" -> A for singular matches, B for plural matches
#   applies_to: "text" | "image" | "both"
RULES_DATA = [
    {
        "rule_id": 1,
        "violation_type": "Terminology",
        "severity": "Medium",
        "rule_cited": "Brand Rule 1: Official brand capitalization is 'ClaimLoom'",
        "source_ref": "Brand Guide, p.2 (Section 1.1)",
        "rule_text": "Always write the brand name as 'ClaimLoom'. Never write 'claim-loom', 'Claim Loom', or 'claimloom'.",
        "regex_pattern": r"(?i)\bclaim[- ]?loom\b",  # <-- UPDATED: catches claim-loom, claim loom, claimloom case-insensitively
        "default_fix": "ClaimLoom",
        "claim_status": None
    },
    {
        "rule_id": 2,
        "violation_type": "Factual",
        "severity": "High",
        "rule_cited": "Brand Rule 2: Certified battery range is 110 km",
        "source_ref": "Product Fact Sheet 2026, p.1 (Spec #4)",
        "rule_text": "Maximum certified battery range is 110 km per charge under standard testing conditions. Never claim 150 km, 200 km, or higher.",
        "regex_pattern": r"(?i)\b(1[2-9]\d|[2-9]\d\d)\s*km\b",  # <-- UPDATED: catches any range over 119 km like 200 km
        "default_fix": "110 km certified range",
        "claim_status": "Outdated Spec"
    },
    {
        "rule_id": 3, "violation_type": "Terminology", "severity": "Low",
        "rule_cited": "Brand Rule 3: Refer to users as 'Creators' or 'Team Members'",
        "source_ref": "Brand Guide, p.5 (Voice & Vocabulary)",
        "rule_text": "Never refer to our users as 'Clients' or 'Consumers'. Always use 'Creators' or 'Team Members'.",
        "regex_pattern": r"(?i)\b(?:client|consumer)s?\b",
        "default_fix": "Creator|Creators", "claim_status": None, "allowed_numbers": None, "applies_to": "text",
    },
    {
        "rule_id": 4, "violation_type": "Tone", "severity": "Medium",
        "rule_cited": "Brand Rule 4: Empowering, professional, non-aggressive tone",
        "source_ref": "Brand Guide, p.3 (Tone of Voice)",
        "rule_text": "Maintain a supportive, clear, professional tone. Avoid fear-mongering, insults to competitors, or hype slang.",
        "regex_pattern": None, "default_fix": None, "claim_status": None, "allowed_numbers": None, "applies_to": "text",
    },
    {
        "rule_id": 5, "violation_type": "Factual", "severity": "High",
        "rule_cited": "Brand Rule 5: Pro Plan pricing is $29/month",
        "source_ref": "Approved Pricing Sheet Q4, p.1",
        "rule_text": "The ClaimLoom Pro Plan costs $29/month (or $290/year). Any other Pro price is outdated.",
        "regex_pattern": r"(?i)\bpro(?:\s+plan)?\b[^.!?\n]{0,40}?(?P<flag>\$\s?(?P<num>\d+(?:\.\d{1,2})?)\s*(?:/|per)\s*(?:month|mo)\b)",
        "default_fix": "$29/month", "claim_status": "Outdated Spec", "allowed_numbers": "29", "applies_to": "text",
    },
    {
        "rule_id": 6, "violation_type": "Accessibility", "severity": "Low",
        "rule_cited": "Brand Rule 6: Inclusive & accessible directional language",
        "source_ref": "Accessibility Handbook, p.8 (WCAG 1.3.3)",
        "rule_text": "Do not use sensory/directional instructions like 'click the green button on the right'. Refer to elements by their explicit text label.",
        "regex_pattern": r"(?i)\b(?:click|press|tap|select)\s+the\s+(?:\w+\s+)?button\s+(?:on\s+the\s+(?:left|right)|at\s+the\s+(?:top|bottom))",
        "default_fix": "select the 'Submit' button", "claim_status": None, "allowed_numbers": None, "applies_to": "text",
    },
    {
        "rule_id": 7, "violation_type": "Factual", "severity": "High",
        "rule_cited": "Brand Rule 7: No absolute guarantees or zero-risk claims",
        "source_ref": "Brand Guide, p.4 (Legal & Promotional Claims)",
        "rule_text": "Never make absolute promotional claims such as '100% guarantee', 'guaranteed 100% results', '100% accident-proof', 'risk-free' or 'zero risk'.",
        "regex_pattern": r"(?i)\b(?:guaranteed\s+100%\s+results|100%\s+(?:guarantee[d]?|accident-proof|safe|risk[- ]free)|zero[- ]risk|risk[- ]free|no\s+risk)\b",
        "default_fix": "proven results", "claim_status": "Unverified Promotional Claim", "allowed_numbers": None, "applies_to": "text",
    },
    {
        "rule_id": 8, "violation_type": "Factual", "severity": "Medium",
        "rule_cited": "Brand Rule 8: Fast-charging spec is 0 to 80% in 45 minutes",
        "source_ref": "Product Fact Sheet 2026, p.2 (Spec #9)",
        "rule_text": "Fast charging reaches 80% in 45 minutes. Never claim full charge in 10 or 15 minutes.",
        "regex_pattern": r"(?i)(?P<flag>(?:fully\s+charged?|full\s+charge|charges?\s+(?:fully|to\s+100%)|0\s*(?:-|to)\s*100%)\s+(?:in|within|under|just)\s+(?:only\s+)?\d{1,2}\s*(?:min|minutes))",
        "default_fix": "charges to 80% in 45 minutes", "claim_status": "Unverified Promotional Claim", "allowed_numbers": None, "applies_to": "text",
    },
    {
        "rule_id": 9, "violation_type": "Visual", "severity": "Medium",
        "rule_cited": "Brand Rule 9: Use only the approved brand color palette",
        "source_ref": "Visual Design System, p.6",
        "rule_text": "Graphics must use the approved palette: Indium Blue (#1E3A8A), Stark Orange (#FF5500), White and Slate (#0F172A).",
        "regex_pattern": None, "default_fix": None, "claim_status": None, "allowed_numbers": None, "applies_to": "image",
    },
    {
        "rule_id": 10, "violation_type": "Accessibility", "severity": "Medium",
        "rule_cited": "Brand Rule 10: Text contrast must meet WCAG 2.1 AA (4.5:1)",
        "source_ref": "Accessibility Handbook, p.4 (WCAG 1.4.3)",
        "rule_text": "Text must have a contrast ratio of at least 4.5:1 against its background.",
        "regex_pattern": None, "default_fix": None, "claim_status": None, "allowed_numbers": None, "applies_to": "image",
    },
    {
        "rule_id": 11, "violation_type": "Terminology", "severity": "Low",
        "rule_cited": "Brand Rule 11: Plan names are capitalized ('Pro Plan')",
        "source_ref": "Brand Guide, p.2 (Section 1.3)",
        "rule_text": "Always capitalize product plan names, for example 'Pro Plan', never 'pro plan'.",
        "regex_pattern": r"\b(?:pro plan|Pro plan|pro Plan)\b",
        "default_fix": "Pro Plan", "claim_status": None, "allowed_numbers": None, "applies_to": "text",
    },
    {
        "rule_id": 12, "violation_type": "Factual", "severity": "Medium",
        "rule_cited": "Brand Rule 12: Warranty is 3 years or 30,000 km",
        "source_ref": "Warranty Policy Doc, p.3",
        "rule_text": "The standard warranty covers 3 years or 30,000 km. Never promise a 'lifetime warranty'.",
        "regex_pattern": r"(?i)\blifetime\s+warranty\b",
        "default_fix": "3-year warranty", "claim_status": "Unverified Promotional Claim", "allowed_numbers": None, "applies_to": "text",
    },
    {
        "rule_id": 13, "violation_type": "Factual", "severity": "Medium",
        "rule_cited": "Brand Rule 13: No unsupported superlatives",
        "source_ref": "Brand Guide, p.4 (Legal & Promotional Claims)",
        "rule_text": "Do not claim to be 'the best', 'the fastest' or 'number one' unless an approved fact sheet proves it.",
        "regex_pattern": r"(?i)\b(?:world'?s\s+(?:best|fastest|first)|best[- ]in[- ](?:class|the[- ]world)|number\s+one|fastest\s+in\s+the\s+(?:world|industry|market))\b",
        "default_fix": "a trusted choice", "claim_status": "Unverified Promotional Claim", "allowed_numbers": None, "applies_to": "text",
    },
    {
        "rule_id": 14, "violation_type": "Tone", "severity": "Low",
        "rule_cited": "Brand Rule 14: One exclamation mark at most",
        "source_ref": "Brand Guide, p.3 (Tone of Voice)",
        "rule_text": "Avoid stacked exclamation marks. Use a single '!' at most.",
        "regex_pattern": r"!{2,}",
        "default_fix": "!", "claim_status": None, "allowed_numbers": None, "applies_to": "text",
    },
    {
        "rule_id": 15, "violation_type": "Tone", "severity": "Low",
        "rule_cited": "Brand Rule 15: No hype slang",
        "source_ref": "Brand Guide, p.3 (Tone of Voice)",
        "rule_text": "Avoid hype slang such as 'insane', 'game-changer', 'killer deal' or 'mind-blowing'.",
        "regex_pattern": r"(?i)\b(?:insane|crazy\s+good|game[- ]?changer|killer\s+deal|mind[- ]?blowing)\b",
        "default_fix": "impressive", "claim_status": None, "allowed_numbers": None, "applies_to": "text",
    },
    {
        "rule_id": 16, "violation_type": "Accessibility", "severity": "Low",
        "rule_cited": "Brand Rule 16: Descriptive link text (no 'click here')",
        "source_ref": "Accessibility Handbook, p.9 (WCAG 2.4.4)",
        "rule_text": "Link text must describe its destination. Do not use 'click here'.",
        "regex_pattern": r"(?i)\bclick\s+here\b",
        "default_fix": "read the full guide", "claim_status": None, "allowed_numbers": None, "applies_to": "text",
    },
]

FACTS_DATA = [
    {"fact_id": 101, "fact_text": "Certified battery range is 110 km per charge under IDC standard testing.", "source_ref": "Product Fact Sheet 2026, p.1"},
    {"fact_id": 102, "fact_text": "Fast charger replenishes battery from 0% to 80% in 45 minutes.", "source_ref": "Product Fact Sheet 2026, p.2"},
    {"fact_id": 103, "fact_text": "ClaimLoom Pro Plan subscription price is $29/month or $290/year.", "source_ref": "Approved Pricing Sheet Q4, p.1"},
    {"fact_id": 104, "fact_text": "Standard product warranty covers 3 years or 30,000 km.", "source_ref": "Warranty Policy Doc, p.3"},
    {"fact_id": 105, "fact_text": "Official brand hex palette is Indium Blue (#1E3A8A) and Stark Orange (#FF5500).", "source_ref": "Visual Design System, p.6"},
]

DEMO_FLAG_EVENTS = [
    ("scan_demo1", 3, "Overridden", "Client is part of a B2B legal quote"),
    ("scan_demo2", 3, "Overridden", "Enterprise contract uses the word Client"),
    ("scan_demo3", 3, "Accepted", ""),
    ("scan_demo4", 7, "Accepted", ""),
    ("scan_demo5", 2, "Accepted", ""),
]

# Define your rule columns explicitly so they match your dictionaries
RULE_COLUMNS = [
    "rule_id",
    "violation_type",
    "severity",
    "rule_cited",
    "source_ref",
    "rule_text",
    "regex_pattern",
    "default_fix",
    "claim_status"
]


def seed_neon_database():
    import psycopg2

    db_url = os.getenv("DATABASE_URL")
    if not db_url or "ep-xyz" in db_url or "user:password" in db_url:
        print("No real DATABASE_URL set. Skipping seed (the app will use the local fallback lists).")
        return

    conn = psycopg2.connect(db_url, connect_timeout=10)
    cur = conn.cursor()
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    cur.execute("""CREATE TABLE IF NOT EXISTS brand_rules (
        rule_id INT PRIMARY KEY, violation_type VARCHAR(50), severity VARCHAR(20), rule_cited TEXT,
        source_ref TEXT, rule_text TEXT, regex_pattern TEXT, default_fix TEXT, claim_status VARCHAR(50));""")
    # These two ALTERs upgrade tables that were created with the older schema:
    cur.execute("ALTER TABLE brand_rules ADD COLUMN IF NOT EXISTS allowed_numbers TEXT;")
    cur.execute("ALTER TABLE brand_rules ADD COLUMN IF NOT EXISTS applies_to VARCHAR(10) DEFAULT 'text';")

    cur.execute("""CREATE TABLE IF NOT EXISTS facts (
        fact_id INT PRIMARY KEY, fact_text TEXT, source_ref TEXT);""")

    cur.execute("""CREATE TABLE IF NOT EXISTS scans (
        scan_id VARCHAR(50) PRIMARY KEY, readiness_score INT, status VARCHAR(30),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);""")
    cur.execute("ALTER TABLE scans ADD COLUMN IF NOT EXISTS input_type VARCHAR(10) DEFAULT 'text';")
    cur.execute("ALTER TABLE scans ADD COLUMN IF NOT EXISTS payload JSONB;")

    cur.execute("""CREATE TABLE IF NOT EXISTS flag_events (
        event_id SERIAL PRIMARY KEY, scan_id VARCHAR(50), rule_id INT, action VARCHAR(20),
        reason TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);""")

    cols = ", ".join(RULE_COLUMNS)
    marks = ", ".join(["%s"] * len(RULE_COLUMNS))
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in RULE_COLUMNS if c != "rule_id")  # update EVERY column
    for r in RULES_DATA:
        cur.execute(
            f"INSERT INTO brand_rules ({cols}) VALUES ({marks}) ON CONFLICT (rule_id) DO UPDATE SET {updates};",
            [r[c] for c in RULE_COLUMNS],
        )
    for f in FACTS_DATA:
        cur.execute(
            """INSERT INTO facts (fact_id, fact_text, source_ref) VALUES (%s, %s, %s)
               ON CONFLICT (fact_id) DO UPDATE SET fact_text = EXCLUDED.fact_text, source_ref = EXCLUDED.source_ref;""",
            (f["fact_id"], f["fact_text"], f["source_ref"]),
        )

    cur.execute("SELECT COUNT(*) FROM flag_events;")
    if cur.fetchone()[0] == 0:
        for ev in DEMO_FLAG_EVENTS:
            cur.execute("INSERT INTO flag_events (scan_id, rule_id, action, reason) VALUES (%s, %s, %s, %s);", ev)

    conn.commit()
    cur.close()
    conn.close()
    print(f"Neon seeded: {len(RULES_DATA)} rules, {len(FACTS_DATA)} facts, tables scans + flag_events ready.")


if __name__ == "__main__":
    seed_neon_database()
