from datetime import UTC, datetime


def utcnow() -> datetime:
    """Current UTC time as a naive datetime, matching the database columns."""
    return datetime.now(UTC).replace(tzinfo=None)
