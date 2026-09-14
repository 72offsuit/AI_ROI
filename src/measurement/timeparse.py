"""Parses RFC 3339 timestamps without depending on the runtime's version.

Why this module exists (issue #62, review finding M3): `datetime.fromisoformat()`
did not accept a trailing `Z` until Python 3.11 (bpo-35829). The SRS declares
`Target Runtime: Python 3.10+` while five call sites handed it `Z`-suffixed values
straight from the contract. CI pins 3.12, so the mismatch never showed up -- the
declaration and the reality had simply never been compared.

★ Why a module of its own. The five callers all sit at or below the contract layer
  (`schema.py`), and `schema.py` is a GATE 1 canonical file -- changing it means
  re-recording the seal, which is a human signature (`FREEZE-003` territory). This
  module sits below everything and imports nothing from the package, so it can be
  shared without touching the seal.

★ Why not just bump the declaration to 3.12 instead. That was the other option in
  issue #62, and it is blocked: the SRS lives in `Plan/`, a read-only submodule.
  But the fix is worth having on any version regardless -- `Z` is valid RFC 3339
  and the contract emits it, so relying on a particular interpreter's tolerance
  was the wrong shape. Parsing explicitly says what the code accepts.
"""

from __future__ import annotations

from datetime import datetime

#: RFC 3339 allows `Z` for UTC; `datetime.fromisoformat` wants `+00:00` before 3.11.
#: Only a trailing `Z` is rewritten -- a `Z` anywhere else is not a UTC marker and
#: must still fail, rather than being quietly repaired into something that parses.
_UTC_SUFFIX = "Z"
_UTC_OFFSET = "+00:00"


def normalize_utc_suffix(value: str) -> str:
    """`…Z` → `…+00:00`. Any other string is returned unchanged.

        >>> normalize_utc_suffix("2025-10-01T23:30:00.000Z")
        '2025-10-01T23:30:00.000+00:00'
        >>> normalize_utc_suffix("2025-10-01T09:00:00.000+09:00")
        '2025-10-01T09:00:00.000+09:00'
        >>> normalize_utc_suffix("Z")
        'Z'
    """
    if len(value) > 1 and value.endswith(_UTC_SUFFIX):
        return value[: -len(_UTC_SUFFIX)] + _UTC_OFFSET
    return value


def parse_datetime(value: str) -> datetime:
    """`datetime.fromisoformat` with the `Z` suffix accepted on every version.

    Raises `ValueError` for anything else, exactly as `fromisoformat` does -- the
    callers rely on that to tell "unparseable" apart from "parsed but no offset",
    and swallowing it here would erase the difference.

        >>> parse_datetime("2025-10-01T23:30:00.000Z").tzinfo is not None
        True
        >>> parse_datetime("2025-10-01T23:30:00")     # naive, still parses
        datetime.datetime(2025, 10, 1, 23, 30)
    """
    return datetime.fromisoformat(normalize_utc_suffix(value))
