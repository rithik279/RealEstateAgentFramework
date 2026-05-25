"""
Backfill area labels on all leads from their phone_e164 area code.
Deterministic — no AI. Safe to re-run (idempotent).

Usage:
    PYTHONPATH=. python scripts/backfill_area_labels.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db import create_database, migrate
from app.orchestrator.area import label_from_e164


def main() -> None:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    db = create_database(db_url)
    migrate(db)  # ensures area column exists

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("select id, phone_e164 from leads")
            leads = cur.fetchall()

    print(f"Total leads: {len(leads)}")

    updates: list[tuple[str, str]] = []
    stats: Counter = Counter()

    for (lead_id, phone_e164) in leads:
        area = label_from_e164(phone_e164)
        updates.append((area, lead_id))
        stats[area or "null"] += 1

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "update leads set area = %s where id = %s",
                updates,
            )
        conn.commit()

    print("\nArea breakdown:")
    for area, count in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {area or 'null':20s} {count}")
    print(f"\nDone. {len(updates)} leads labeled.")


if __name__ == "__main__":
    main()
