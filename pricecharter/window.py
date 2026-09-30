import re
from datetime import datetime, timedelta


def deadline_from(until: str, now: datetime | None = None) -> datetime:
    """Next occurrence of local HH:MM after `now` (tomorrow if it already passed today)."""
    m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", until.strip())
    if not m:
        raise ValueError(f"expected HH:MM, got {until!r}")
    now = now or datetime.now()
    target = now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
    return target if target > now else target + timedelta(days=1)
