"""
Create a one-time invitation code for invite-only sign-up
(REGISTRATION_MODE=invite). Give the printed code to the clinician; only
its hash is stored.

Usage (from backend/):
    .venv/Scripts/python.exe scripts/create_invite.py [--email dr@hospital.org] [--days 14]
"""

import argparse
import sys
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", help="restrict the code to this email address")
    ap.add_argument("--days", type=int, default=14, help="days until the code expires")
    args = ap.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from app.db import SessionLocal
    from app.services.auth_service import create_invite

    with SessionLocal() as db:
        code = create_invite(db, email=args.email, days=args.days)
    print(f"Invitation code (valid {args.days} days{', for ' + args.email if args.email else ''}): {code}")


if __name__ == "__main__":
    main()
