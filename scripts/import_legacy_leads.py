"""
Import legacy leads from CSV files into Postgres + enqueue call_lead jobs.

Usage:
    PYTHONPATH=. python scripts/import_legacy_leads.py

Env vars required:
    DATABASE_URL - Postgres connection string
"""
from __future__ import annotations

import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db import create_database, migrate
from app.orchestrator.phone import normalize_na_phone_to_e164
from app.orchestrator.repository import OrchestratorRepo
from app.orchestrator.schedule import CallWindow


def main() -> None:
    if not os.getenv("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    db = create_database(os.getenv("DATABASE_URL"))
    migrate(db)
    repo = OrchestratorRepo(db=db)

    call_window = CallWindow(
        tz="America/Toronto",
        start_hour=9,
        end_hour=20,
    )
    now_utc = datetime.now(timezone.utc)

    files = [
        Path(__file__).parent.parent / "_Anu - Leads Assignment  - importLeads.csv",
        Path(__file__).parent.parent / "Old RE Leads for Reactivation.csv",
    ]

    total_inserted = 0
    total_skipped = 0
    total_jobs = 0

    for filepath in files:
        if not filepath.exists():
            print(f"SKIP: {filepath.name} not found")
            continue

        print(f"\nProcessing: {filepath.name}")
        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = (row.get("Customer Name") or row.get("Name") or "").strip()
                phone_raw = (row.get("Contact Number") or row.get("Phone") or "").strip()
                email = (row.get("Email") or "").strip()
                source = "legacy_reactivation"

                phone_e164 = normalize_na_phone_to_e164(phone_raw)
                if not phone_e164:
                    print(f"  SKIP (bad phone): {name} | {phone_raw}")
                    total_skipped += 1
                    continue

                # Insert with dedup by phone_e164
                lead_id = str(uuid4())
                with db.connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            insert into leads (id, source, name, phone_e164, email, consent_text, language, status)
                            values (%s,%s,%s,%s,%s,%s,%s,%s)
                            on conflict do nothing
                            """,
                            (
                                lead_id,
                                source,
                                name or None,
                                phone_e164,
                                email or None,
                                "Legacy lead import",
                                "en",
                                "new",
                            ),
                        )
                    conn.commit()

                # Check if inserted (if existing, we still get ID for job)
                with db.connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "select id from leads where phone_e164=%s order by created_at desc limit 1",
                            (phone_e164,),
                        )
                        row_result = cur.fetchone()
                        if row_result:
                            lead_id = str(row_result[0])

                # Schedule call at next call window
                run_at = call_window.next_allowed(now_utc)
                repo.enqueue_job(
                    job_type="call_lead",
                    dedupe_key=f"lead:{lead_id}:call",
                    payload={"lead_id": lead_id},
                    run_at=run_at,
                    max_attempts=3,
                )
                repo.add_event(
                    lead_id=lead_id,
                    event_type="legacy_lead_imported",
                    payload={"source_file": filepath.name, "name": name, "phone": phone_e164},
                )

                print(f"  + {name} | {phone_e164} → call @ {run_at.isoformat()}")
                total_inserted += 1
                total_jobs += 1

    print(f"\nDone.")
    print(f"  Inserted: {total_inserted}")
    print(f"  Skipped: {total_skipped}")
    print(f"  Jobs enqueued: {total_jobs}")


if __name__ == "__main__":
    main()
