from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from src.measurement.sink import KST

DAY_MS = 86_400_000
SESSION_TIMEOUT_MS = 30 * 60_000

_KST_OFFSET_MS = 9 * 3_600_000
_EPOCH_ORDINAL = date(1970, 1, 1).toordinal()
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_ONE_MS = timedelta(milliseconds=1)


def kst_midnight_ms(day: date) -> int:
    return (day.toordinal() - _EPOCH_ORDINAL) * DAY_MS - _KST_OFFSET_MS


def timestamp(ms: int) -> str:
    days, rest = divmod(ms + _KST_OFFSET_MS, DAY_MS)
    seconds, millis = divmod(rest, 1000)
    minutes, sec = divmod(seconds, 60)
    hours, minute = divmod(minutes, 60)
    day = date.fromordinal(_EPOCH_ORDINAL + days).isoformat()
    return f"{day}T{hours:02d}:{minute:02d}:{sec:02d}.{millis:03d}+09:00"


def to_datetime(ms: int) -> datetime:
    return (_EPOCH + timedelta(milliseconds=ms)).astimezone(KST)


def ceil_ms(moment: datetime) -> int:
    return -((_EPOCH - moment) // _ONE_MS)
