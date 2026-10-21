"""D1 semantic/2 TLV primitives. No model or storage-format dependency."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import math
import re
import struct
from typing import Any

from src.measurement.timeparse import parse_datetime

SERIALIZATION = "d1-semantic/2-proposed"


class D1ContractError(ValueError):
    """An explicit contract mismatch; never a missing value or an empty success."""


@dataclass(frozen=True)
class Float32:
    value: float


@dataclass(frozen=True)
class Float64:
    value: float


def require(condition: bool, message: str) -> None:
    if not condition:
        raise D1ContractError(message)


def normalize_timestamp(value: str, *, syntax_message: str =
                        "timestamp: offset and at most six fractional digits required") -> str:
    """Validate the D1 text grammar before parsing; retain every allowed microsecond."""
    match = re.fullmatch(
        r"([0-9]{4}-[0-9]{2}-[0-9]{2}T([0-9]{2}):([0-9]{2}):([0-9]{2}))"
        r"(?:\.([0-9]{1,6}))?(Z|[+-][0-9]{2}:[0-9]{2})", value)
    require(match is not None, syntax_message)
    require(int(match.group(2)) < 24 and int(match.group(3)) < 60 and int(match.group(4)) < 60,
            "timestamp: invalid clock components")
    offset = match.group(6)
    if offset != "Z":
        require(int(offset[1:3]) < 24 and int(offset[4:]) < 60,
                "timestamp: invalid offset components")
    fraction = match.group(5)
    return match.group(1) + ("." + fraction.ljust(6, "0") if fraction else "") + offset


def instant(value: str | datetime) -> datetime:
    if isinstance(value, str):
        normalized = normalize_timestamp(value)
        try:
            value = parse_datetime(normalized)
        except (ValueError, TypeError) as exc:
            raise D1ContractError("invalid timestamp") from exc
    require(isinstance(value, datetime) and value.utcoffset() is not None,
            "timestamp must be offset-aware")
    return value.astimezone(timezone.utc)


def calendar_date(value: str | date) -> date:
    if isinstance(value, str):
        require(bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)), "invalid date syntax")
        try:
            value = date(*map(int, value.split("-")))
        except ValueError as exc:
            raise D1ContractError("invalid calendar date") from exc
    require(type(value) is date, "date must not contain a time")
    return value


def _frame(tag: int, payload: bytes) -> bytes:
    return bytes([tag]) + len(payload).to_bytes(8, "big") + payload


def _float(value: Any, width: int) -> bytes:
    require(type(value) in (int, float), "invalid float type")
    try:
        finite = math.isfinite(value)
    except OverflowError as exc:
        raise D1ContractError("float out of range") from exc
    require(finite, "non-finite/invalid float")
    value = 0.0 if value == 0 else value
    try:
        payload = struct.pack(">f" if width == 4 else ">d", value)
    except (OverflowError, struct.error) as exc:
        raise D1ContractError("float out of range") from exc
    converted = struct.unpack(">f" if width == 4 else ">d", payload)[0]
    require(math.isfinite(converted),
            "float became non-finite")
    if converted == 0:
        payload = bytes(width)
    return _frame(4 if width == 4 else 3, payload)


def tlv(value: Any) -> bytes:
    if value is None:
        return _frame(0, b"")
    if type(value) is bool:
        return _frame(1, bytes([int(value)]))
    if type(value) is int:
        require(-(2**63) <= value < 2**63, "integer outside Int64")
        return _frame(2, value.to_bytes(8, "big", signed=True))
    if isinstance(value, Float32):
        return _float(value.value, 4)
    if isinstance(value, Float64):
        return _float(value.value, 8)
    if type(value) is float:
        return _float(value, 8)
    if type(value) is str:
        try:
            return _frame(5, value.encode("utf-8", errors="strict"))
        except UnicodeError as exc:
            raise D1ContractError("invalid UTF-8 string") from exc
    if isinstance(value, datetime):
        delta = instant(value) - datetime(1970, 1, 1, tzinfo=timezone.utc)
        micros = (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds
        return _frame(7, micros.to_bytes(8, "big", signed=True))
    if type(value) is date:
        return _frame(6, value.isoformat().encode("ascii"))
    if type(value) in (list, tuple):
        return _frame(8, b"".join(tlv(item) for item in value))
    if type(value) is dict:
        require(all(type(key) is str for key in value), "map keys must be strings")
        try:
            keys = sorted(value, key=lambda key: key.encode("utf-8", errors="strict"))
        except UnicodeError as exc:
            raise D1ContractError("invalid UTF-8 key") from exc
        return _frame(9, b"".join(tlv(key) + tlv(value[key]) for key in keys))
    if type(value) is bytes:
        return _frame(10, value)
    raise D1ContractError(f"unsupported TLV type: {type(value).__name__}")


def canonical_set(values: list[Any]) -> list[Any]:
    """Order an explicitly declared set, rejecting duplicate semantic members."""
    encoded = [(tlv(value), value) for value in values]
    require(len({key for key, _ in encoded}) == len(encoded), "duplicate set member")
    return [value for _, value in sorted(encoded, key=lambda pair: pair[0])]


def semantic_hash(domain: str, body: Any) -> str:
    require(type(domain) is str and bool(domain), "missing hash domain")
    return hashlib.sha256(tlv({
        "serialization": SERIALIZATION, "domain": domain, "body": body,
    })).hexdigest()


def file_sha256(data: bytes) -> str:
    require(type(data) is bytes, "file hash requires exact bytes")
    return hashlib.sha256(data).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in out, "duplicate JSON key")
        out[key] = value
    return out


def strict_json(data: bytes) -> Any:
    def nonfinite(value: str) -> None:
        raise D1ContractError(f"non-finite JSON number: {value}")
    try:
        result = json.loads(data.decode("utf-8", errors="strict"),
                            object_pairs_hook=_pairs, parse_constant=nonfinite)
        # Also rejects lone surrogate strings and exponent overflow such as 1e999.
        tlv(result)
        return result
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise D1ContractError("invalid UTF-8 JSON") from exc


def project(value: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    require(type(value) is dict, "record must be an object")
    require(all(name in value for name in fields), f"missing required fields: {fields}")
    return {name: value[name] for name in fields}
