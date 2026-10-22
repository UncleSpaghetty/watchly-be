from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

ROME = ZoneInfo("Europe/Rome")


def to_local_date(value: datetime, tz: ZoneInfo = ROME) -> date:
    return value.astimezone(tz).date()


def now_local(tz: ZoneInfo = ROME) -> datetime:
    return datetime.now(UTC).astimezone(tz)


def get_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:
        return ROME
