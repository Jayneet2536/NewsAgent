from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


def parse_timestamp(value: object) -> datetime | None:
    """Only use timestamps with time and timezone for exact window filtering."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(value)
            except (TypeError, ValueError, OverflowError):
                return None
    else:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def in_window(published_at: datetime | None, start: datetime, end: datetime) -> bool:
    return published_at is None or start <= published_at <= end
