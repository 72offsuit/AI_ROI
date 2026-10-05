from __future__ import annotations

PRODUCED_EVENT_TYPES = (
    "session_start",
    "page_view",
    "product_view",
    "add_to_cart",
    "remove_from_cart",
)

VISIT_P = (1, 4)
CONTINUE_P = (3, 4)
MAX_ACTIONS_PER_SESSION = 12
ACTION_DELAY_MS = (1_000, 300_000)
ACTIONS = ("page_view", "product_view", "add_to_cart", "remove_from_cart")
ACTION_WEIGHTS = (3, 4, 2, 1)
PAGE_VIEW_PAGES = ("home", "list", "history", "cart")
ADD_QUANTITY = (1, 4)
RECENT_VIEWS_CAP = 20


def visit_probability(customer_id: str) -> tuple[int, int]:
    return VISIT_P
