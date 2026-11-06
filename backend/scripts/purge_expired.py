"""
Retention: delete analyses older than RETENTION_DAYS, with their photos,
heatmaps and reports. Run daily (cron, Cloud Scheduler). Does nothing when
RETENTION_DAYS is 0.

Usage (from backend/):
    .venv/Scripts/python.exe scripts/purge_expired.py [--days N]
"""

import argparse
import sys
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, help="override RETENTION_DAYS")
    args = ap.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from app.core.config import settings
    from app.db import SessionLocal
    from app.services import audit
    from app.services.prediction_service import PredictionService

    days = args.days if args.days is not None else settings.RETENTION_DAYS
    if days <= 0:
        print("RETENTION_DAYS is 0: analyses are kept; nothing deleted.")
        return
    with SessionLocal() as db:
        removed = PredictionService(db).purge_older_than(days)
        audit.record(db, f"retention_purge_{removed}")
    print(f"Deleted {removed} analyses older than {days} days.")


if __name__ == "__main__":
    main()
