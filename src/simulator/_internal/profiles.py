from __future__ import annotations

from datetime import date

_CALENDAR_START = date(2025, 1, 1)
_CART_LIFETIME_DAYS = 30

PROFILES: dict[str, dict[str, object]] = {
    name: {"calendar_start": _CALENDAR_START, "cart_lifetime_days": _CART_LIFETIME_DAYS}
    for name in ("smoke", "short", "reference", "long", "rolling")
}
