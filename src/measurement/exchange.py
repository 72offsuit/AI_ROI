"""커머스 교환 파일 읽기 — `docs/contracts/commerce-exchange/v1/` (이슈 #100).

`purchase` 이벤트는 주문 단위 1행이라 품목·원가·할인을 싣지 않는다. 그 셋을
`data/commerce/` 의 비이벤트 JSONL 묶음이 싣고, 이 모듈이 그것을 주문별로 묶어
`economics.OrderItem` 으로 돌려준다. 이벤트 계약(`schema.py`, GATE 1 정본)은
건드리지 않는다.

## 읽기 규칙

- 디렉터리가 **없으면 `None`** 이다. 오늘의 정상 상태이고, 받는 쪽이 `not_run` ·
  `NO_COST_BASIS` 로 말한다. 빈 묶음으로 바꾸지 않는다 — 빈 묶음은 "주문이 0건"
  이라는 측정값이 된다.
- 있는데 형식이 틀리면 **묶음 전체를 거부한다** (`ExchangeContractError`). 한 행만
  빼고 읽으면 COGS 가 일부 주문의 합계인데 전체처럼 보인다.
- 품목이 없는 주문은 거부하지 않는다. 형식 위반이 아니라 **`DQ-09` 위반**이고,
  그 판정은 `validate.py` 가 한다.

런타임 의존성이 없다. `jsonschema` 는 dev 의존성이라 여기서 쓰지 않고, 필드별
형식을 직접 검사한다 — 스키마 파일과의 일치는 `tests/test_commerce_exchange_contract.py`
가 대조한다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Mapping

from src.measurement import economics as ec
from src.measurement import schema as sc
from src.measurement import timeparse as tp
from src.measurement.errors import ExchangeContractError

CONTRACT_ID = "commerce-exchange/v1"
FILES = ("customers", "catalog", "orders", "order_items")

_KST = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?\+09:00$"
_DATE = r"^\d{4}-\d{2}-\d{2}$"
_CATEGORIES = frozenset(item.value for item in sc.Category)


def _pattern(regex: str) -> Callable[[object], bool]:
    compiled = re.compile(regex)
    return lambda value: isinstance(value, str) and compiled.fullmatch(value) is not None


def _amount(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _nullable_amount(value: object) -> bool:
    return value is None or _amount(value)


def _positive(value: object) -> bool:
    return _amount(value) and value >= 1  # type: ignore[operator]


def _text(value: object) -> bool:
    return isinstance(value, str) and value != ""


#: 파일별 필드 → 검사. **필수 필드 집합이 곧 이 dict 의 키**이고, 선택 필드는
#: `_OPTIONAL` 에 따로 둔다. 스키마 파일의 `required` 와의 일치는 테스트가 본다.
FIELDS: dict[str, dict[str, Callable[[object], bool]]] = {
    "customers": {
        "customer_id": _pattern(sc.IDENTIFIER_PATTERNS["customer_id"]),
        "signup_date": _pattern(_DATE),
    },
    "catalog": {
        "snapshot_at": _pattern(_KST),
        "product_id": _pattern(sc.IDENTIFIER_PATTERNS["product_id"]),
        "category": lambda value: value in _CATEGORIES,
        "selling_price": _amount,
        "unit_cost": _nullable_amount,
    },
    "orders": {
        "order_id": _pattern(sc.IDENTIFIER_PATTERNS["order_id"]),
        "customer_id": _pattern(sc.IDENTIFIER_PATTERNS["customer_id"]),
        "ordered_at": _pattern(_KST),
        "order_amount": _amount,
        "discount": _amount,
        "shipping_fee": _amount,
        "shipping_charged": _amount,
    },
    "order_items": {
        "order_id": _pattern(sc.IDENTIFIER_PATTERNS["order_id"]),
        "line_no": _positive,
        "product_id": _pattern(sc.IDENTIFIER_PATTERNS["product_id"]),
        "quantity": _positive,
        "unit_price": _amount,
        "unit_cost": _nullable_amount,
    },
}
_OPTIONAL: dict[str, dict[str, Callable[[object], bool]]] = {
    "catalog": {"name": _text},
}


@dataclass(frozen=True, slots=True)
class ExchangeOrder:
    """교환 파일이 말하는 주문 하나. `items=()` 면 품목이 없다는 뜻이다(`DQ-09` 위반)."""

    order_id: str
    customer_id: str
    order_amount: int
    discount: int
    shipping_fee: int
    shipping_charged: int
    items: tuple[ec.OrderItem, ...]


@dataclass(frozen=True, slots=True)
class CommerceExchange:
    root: Path
    manifest: Mapping[str, object]
    generated_at: datetime
    """묶음을 만든 시각. 명부(`customers`·`catalog`)는 이 시각까지만 책임진다."""
    orders: Mapping[str, ExchangeOrder]
    signup_dates: Mapping[str, date]
    """고객 명부 — `customer_id` → 가입일(KST 날짜)."""
    product_ids: frozenset[str]
    """상품 명부 — 판매 중단 상품도 들어 있다."""


def default_root(source_root: Path) -> Path:
    """Sink 루트(`data/raw`)의 형제 `data/commerce` 다."""
    return source_root.parent / "commerce"


def _fail(root: Path, detail: str) -> ExchangeContractError:
    return ExchangeContractError(
        f"커머스 교환 파일 {root} 이 계약 {CONTRACT_ID} 를 어겼다: {detail}. "
        "묶음 전체를 읽지 않는다 — 일부만 읽으면 합계가 전체처럼 보인다"
    )


def _read_rows(root: Path, name: str) -> list[dict[str, object]]:
    path = root / f"{name}.jsonl"
    if path.is_symlink() or not path.is_file():
        raise _fail(root, f"{path.name} 이 없거나 일반 파일이 아니다")
    required, optional = FIELDS[name], _OPTIONAL.get(name, {})
    rows: list[dict[str, object]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise _fail(root, f"{path.name}:{number} 이 JSON 이 아니다 ({error.msg})") from error
        if not isinstance(row, dict):
            raise _fail(root, f"{path.name}:{number} 이 객체가 아니다")
        missing = sorted(set(required) - set(row))
        unknown = sorted(set(row) - set(required) - set(optional))
        if missing or unknown:
            raise _fail(
                root, f"{path.name}:{number} 필드 누락 {missing} · 계약에 없는 필드 {unknown}"
            )
        bad = sorted(
            key for key, check in {**required, **optional}.items()
            if key in row and not check(row[key])
        )
        if bad:
            raise _fail(root, f"{path.name}:{number} 값이 형식에 맞지 않는 필드 {bad}")
        rows.append(row)
    return rows


def read_exchange(root: Path) -> CommerceExchange | None:
    """`root` 의 교환 묶음을 읽는다. 디렉터리가 없으면 `None` 이다 — 빈 묶음이 아니다."""
    if not root.exists() and not root.is_symlink():
        return None
    if root.is_symlink() or not root.is_dir():
        raise _fail(root, "디렉터리가 아니거나 심볼릭 링크다")

    manifest_path = root / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise _fail(root, "manifest.json 이 없다 — 묶음의 출처·시각·행 수를 알 수 없다")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise _fail(root, f"manifest.json 이 JSON 이 아니다 ({error.msg})") from error
    if not isinstance(manifest, dict) or manifest.get("contract") != CONTRACT_ID:
        raise _fail(root, f"manifest.contract 가 {CONTRACT_ID} 가 아니다")
    if not _pattern(_KST)(manifest.get("generated_at")):
        raise _fail(
            root, "manifest.generated_at 이 KST 오프셋 RFC 3339 가 아니다 — 명부가 "
            "언제까지를 책임지는지 알 수 없다",
        )
    generated_at = tp.parse_datetime(str(manifest["generated_at"]))

    rows = {name: _read_rows(root, name) for name in FILES}
    declared = manifest.get("files")
    if not isinstance(declared, dict):
        raise _fail(root, "manifest.files 가 없다")
    for name, found in rows.items():
        if declared.get(f"{name}.jsonl") != len(found):
            raise _fail(
                root,
                f"{name}.jsonl 이 {len(found)}행인데 매니페스트는 "
                f"{declared.get(f'{name}.jsonl')!r}행이라 한다 — 잘렸거나 섞였다",
            )

    signup_dates: dict[str, date] = {}
    for row in rows["customers"]:
        customer_id = str(row["customer_id"])
        if customer_id in signup_dates:
            raise _fail(root, f"customers.jsonl 에 {customer_id} 가 두 번 있다")
        signup_dates[customer_id] = date.fromisoformat(str(row["signup_date"]))
    product_ids = [str(row["product_id"]) for row in rows["catalog"]]
    if len(set(product_ids)) != len(product_ids):
        raise _fail(root, "catalog.jsonl 에 같은 product_id 가 두 번 있다")

    orders: dict[str, dict[str, object]] = {}
    for row in rows["orders"]:
        order_id = str(row["order_id"])
        if order_id in orders:
            raise _fail(root, f"orders.jsonl 에 {order_id} 가 두 번 있다")
        orders[order_id] = row

    items: dict[str, list[ec.OrderItem]] = {order_id: [] for order_id in orders}
    lines: set[tuple[str, int]] = set()
    for row in sorted(rows["order_items"], key=lambda r: (r["order_id"], r["line_no"])):  # type: ignore[arg-type,return-value]
        order_id, line_no = str(row["order_id"]), int(row["line_no"])  # type: ignore[call-overload]
        if order_id not in orders:
            raise _fail(root, f"order_items.jsonl 의 {order_id} 가 orders.jsonl 에 없다")
        if (order_id, line_no) in lines:
            raise _fail(root, f"order_items.jsonl 에 ({order_id}, {line_no}) 가 두 번 있다")
        lines.add((order_id, line_no))
        items[order_id].append(ec.OrderItem(
            product_id=str(row["product_id"]),
            quantity=int(row["quantity"]),  # type: ignore[call-overload]
            unit_price=int(row["unit_price"]),  # type: ignore[call-overload]
            unit_cost=row["unit_cost"],  # type: ignore[arg-type]
        ))

    return CommerceExchange(
        root=root,
        manifest=manifest,
        generated_at=generated_at,
        signup_dates=signup_dates,
        product_ids=frozenset(product_ids),
        orders={
            order_id: ExchangeOrder(
                order_id=order_id,
                customer_id=str(row["customer_id"]),
                order_amount=int(row["order_amount"]),  # type: ignore[call-overload]
                discount=int(row["discount"]),  # type: ignore[call-overload]
                shipping_fee=int(row["shipping_fee"]),  # type: ignore[call-overload]
                shipping_charged=int(row["shipping_charged"]),  # type: ignore[call-overload]
                items=tuple(items[order_id]),
            )
            for order_id, row in orders.items()
        },
    )
