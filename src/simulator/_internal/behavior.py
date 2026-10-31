from __future__ import annotations

# S4(#143): 구매 퍼널과 처치 노출을 더했다. 모수는 config/simulator_config.yaml 의 behavior 블록(params.py)에 있다.
PRODUCED_EVENT_TYPES = (
    "session_start",
    "page_view",
    "product_view",
    "add_to_cart",
    "remove_from_cart",
    "checkout_start",
    "purchase",
    "campaign_exposed",
    "push_sent",
    "coupon_exposed",
    "coupon_clicked",
    "coupon_use",
    # #198: 부수 이벤트 4종. 규칙은 config behavior.aux_events 와 engine(_search·_due_reviews·_schedule_cs).
    "search",
    "return_visit",
    "review",
    "cs_contact",
)

ACTIONS = ("page_view", "product_view", "add_to_cart", "remove_from_cart")
PAGE_VIEW_PAGES = ("home", "list", "history", "cart")
RECENT_VIEWS_CAP = 20


def visit_probability(customer_id: str) -> tuple[int, int] | None:
    """방문 분수의 시험용 덮어쓰기 지점. `None` 이면 Trait·engagement·처치로 정한다(engine._day_start)."""
    return None
