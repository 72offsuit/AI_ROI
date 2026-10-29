from __future__ import annotations

from datetime import date

_CALENDAR_START = date(2025, 1, 1)
_CART_LIFETIME_DAYS = 30
# 라벨 관찰기간은 프로파일 간에도 고정한다 — 바뀌면 런끼리 Incremental Profit 을 비교할 수 없다(data_spec §2.2).
LABEL_WINDOW_DAYS = 42

# data_spec §2.2 표. T0 = calendar_start + warmup_days. run_days 는 그 프로파일의 권장 총 일수이고
# 강제하지 않는다(rolling 은 최소값). small 은 S3 이슈 #77 의 개발용 규모 이름이고 시간축은 short 와
# 같다 — PRD FR-04 의 "6개월"은 하한으로 읽는다(DR-S3-sample-size U3). API 는 고객 수를 늘 num_customers
# 로 받고(DR-S3-p6-signup U11), 기본 고객 수는 CLI 가 --customers 를 생략했을 때만 쓴다.
_AXES: dict[str, tuple[int, int | None, int]] = {
    # name: (warmup_days, clv_horizon_days, run_days)
    "smoke": (90, None, 140),
    "short": (180, 90, 275),
    "small": (180, 90, 275),
    "reference": (273, 365, 640),
    "long": (365, 730, 1_100),
    "rolling": (273, 365, 900),
}

# FR-04 Small Mode = 5,000명. 여기 없는 프로파일은 고객 수를 늘 명시해야 한다.
_DEFAULT_CUSTOMERS: dict[str, int] = {"small": 5_000}

PROFILES: dict[str, dict[str, object]] = {
    name: {
        "calendar_start": _CALENDAR_START,
        "cart_lifetime_days": _CART_LIFETIME_DAYS,
        "warmup_days": warmup,
        "label_window_days": LABEL_WINDOW_DAYS,
        "clv_horizon_days": clv,
        "run_days": run,
        "default_customers": _DEFAULT_CUSTOMERS.get(name),
    }
    for name, (warmup, clv, run) in _AXES.items()
}


def default_customers(profile: str) -> int | None:
    """프로파일의 기본 고객 수. 기본값이 없거나 모르는 프로파일이면 None 이다."""
    settings = PROFILES.get(profile)
    return None if settings is None else settings["default_customers"]
