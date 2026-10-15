"""Typed, spreadsheet-safe presentation of CSV exports.

Strings (including headers) are protected before ordinary CSV quoting. Typed
numbers keep their signs, booleans use lowercase JSON spelling, and null is an
empty cell. Objects/arrays use compact Unicode JSON in insertion order; native
numeric formatting is retained rather than imposing a new scientific encoding.
These helpers never modify the structured records or immutable bundle bytes.
"""
from __future__ import annotations

import io
import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from typing import Any


# Deliberately explicit: Python's str.isspace and JavaScript's \s disagree.
# This union is also implemented in frontend/lib/csv.ts and covered by the shared
# schema/csv_serialization_cases.json fixture.
CSV_WHITESPACE = (
    "\u0009\u000a\u000b\u000c\u000d\u001c\u001d\u001e\u001f\u0020"
    "\u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005"
    "\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f"
    "\u3000\ufeff"
)


def csv_text(value: Any) -> str:
    """Return display text, protecting string formulas without relabeling numbers."""
    if value is None:
        return ""
    if isinstance(value, str):
        if value.startswith(("\t", "\r", "\n")) or value.lstrip(CSV_WHITESPACE).startswith(("=", "+", "-", "@")):
            return "'" + value
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def escape_csv_cell(value: Any) -> str:
    """Apply string protection, then minimal CSV quoting including both CR and LF."""
    text = csv_text(value)
    if any(character in text for character in (',', '"', '\r', '\n')):
        return '"' + text.replace('"', '""') + '"'
    return text


def rows_to_csv(rows: Iterable[Mapping[str, Any]], columns: Sequence[str]) -> str:
    """Render fixed-order columns while looking up rows using original, unescaped keys.

    Server exports retain their CRLF record terminator and final terminator.
    Per-cell quoting/protection matches the browser contract; no input is mutated.
    """
    output = io.StringIO(newline="")
    output.write(",".join(escape_csv_cell(column) for column in columns) + "\r\n")
    for row in rows:
        output.write(",".join(escape_csv_cell(row.get(column)) for column in columns) + "\r\n")
    return output.getvalue()
