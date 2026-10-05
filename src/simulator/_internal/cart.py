from __future__ import annotations

MAX_QUANTITY = 99

Cart = dict[str, dict[str, int]]


def is_live(item: dict[str, int], at_ms: int, lifetime_ms: int) -> bool:
    return at_ms < item["last_change_ms"] + lifetime_ms


def live_products(cart: Cart, at_ms: int, lifetime_ms: int) -> list[str]:
    return sorted(pid for pid, item in cart.items() if is_live(item, at_ms, lifetime_ms))


def _purge(cart: Cart, at_ms: int, lifetime_ms: int) -> None:
    for pid in sorted(cart):
        if not is_live(cart[pid], at_ms, lifetime_ms):
            del cart[pid]


def add(
    cart: Cart, product_id: str, quantity: int, unit_price: int, at_ms: int, lifetime_ms: int
) -> int:
    _purge(cart, at_ms, lifetime_ms)
    item = cart.get(product_id)
    current = 0 if item is None else item["quantity"]
    added = min(quantity, MAX_QUANTITY - current)
    if added <= 0:
        return 0
    cart[product_id] = {
        "quantity": current + added,
        "last_change_ms": at_ms,
        "unit_price": unit_price,
    }
    return added


def remove(cart: Cart, product_id: str, quantity: int, at_ms: int, lifetime_ms: int) -> int:
    _purge(cart, at_ms, lifetime_ms)
    item = cart.get(product_id)
    if item is None or quantity <= 0:
        return 0
    removed = min(quantity, item["quantity"])
    if removed == item["quantity"]:
        del cart[product_id]
    else:
        item["quantity"] -= removed
        item["last_change_ms"] = at_ms
    return removed
