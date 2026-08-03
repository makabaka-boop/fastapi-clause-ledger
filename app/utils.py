"""Small shared helpers."""

from datetime import datetime, timezone


def now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string.

    Example: ``2026-08-03T09:15:42.123456+00:00``. All persisted and returned
    timestamps use this single format.
    """
    return datetime.now(timezone.utc).isoformat()
