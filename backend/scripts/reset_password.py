"""
Set a new password for an existing account in a local database.

The app has no "forgot password" flow; this is for a developer who can
already reach the database. The new password is typed at a hidden prompt,
never passed on the command line (where it would land in shell history).

Usage (from backend/):
    .venv/Scripts/python.exe scripts/reset_password.py you@example.org
    .venv/Scripts/python.exe scripts/reset_password.py you@example.org --database-url sqlite:///./e2e.db

Without --database-url it uses DATABASE_URL from the environment / .env,
the same database the app uses.
"""

import argparse
import getpass
import os
import sys
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("email")
    ap.add_argument("--database-url", help="defaults to the app's DATABASE_URL")
    args = ap.parse_args()
    if args.database_url:
        # Settings are read at import time, so this must be set first.
        os.environ["DATABASE_URL"] = args.database_url
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from app.core.security import hash_password
    from app.db import SessionLocal
    from app.models.entities import User

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == args.email.strip().lower()).one_or_none()
        if user is None:
            sys.exit(f"No account with email {args.email}")
        password = getpass.getpass("New password: ")
        if not 8 <= len(password) <= 128:  # same rule as registration
            sys.exit("Password must be 8 to 128 characters; nothing changed.")
        if getpass.getpass("Repeat new password: ") != password:
            sys.exit("Passwords did not match; nothing changed.")
        user.password_hash = hash_password(password)
        db.commit()
    print(f"Password updated for {args.email}. Sign in with the new password.")


if __name__ == "__main__":
    main()
