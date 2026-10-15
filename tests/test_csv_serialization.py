"""The same explicit synthetic cases are consumed by the browser's CSV tests."""
from __future__ import annotations

import copy
import csv
import io
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from api.csv_serialization import CSV_WHITESPACE, csv_text, escape_csv_cell, rows_to_csv


FIXTURE = json.loads((Path(__file__).resolve().parents[1] / "schema" / "csv_serialization_cases.json").read_text())


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda case: case["id"])
def test_shared_csv_fixture_exact_text_and_cell_bytes(case):
    value = copy.deepcopy(case["value"])
    assert csv_text(value) == case["expected_text"]
    assert escape_csv_cell(value) == case["expected_cell"]
    assert value == case["value"]
    # A trailing guard cell disambiguates empty CSV fields from empty records.
    rendered = escape_csv_cell(value) + ",guard\r\n"
    assert next(csv.reader(io.StringIO(rendered, newline=""))) == [case["expected_text"], "guard"]


@pytest.mark.parametrize("space", list(CSV_WHITESPACE), ids=lambda value: f"U+{ord(value):04X}")
@pytest.mark.parametrize("operator", "=+-@")
def test_every_explicit_whitespace_character_precedes_dangerous_string(space, operator):
    value = space + operator + "1"
    assert csv_text(value) == "'" + value


def test_headers_and_values_are_escaped_without_changing_keys_or_order():
    columns = [" \ufeff=header", "numeric", "\tordinary", "missing", "details"]
    rows = [{" \ufeff=header": "@formula", "numeric": -2.5, "\tordinary": "line\rvalue",
             "details": {"label": "=nested", "active": False}, "excluded": "not exported"}]
    original = copy.deepcopy(rows)
    result = rows_to_csv(rows, columns)
    reader = csv.reader(io.StringIO(result, newline=""))
    assert next(reader) == ["' \ufeff=header", "numeric", "'\tordinary", "missing", "details"]
    assert next(reader) == ["'@formula", "-2.5", "line\rvalue", "", '{"label":"=nested","active":false}']
    assert list(reader) == []
    assert result.endswith("\r\n")
    assert rows == original


@pytest.mark.parametrize("value,expected", [
    (Decimal("-1.250"), "-1.250"),
    (Decimal("-1E-10"), "-1E-10"),
    (date(2026, 10, 15), "2026-10-15"),
    (datetime(2026, 10, 15, 4, 5, tzinfo=timezone.utc), "2026-10-15T04:05:00+00:00"),
    (UUID("00000000-0000-0000-0000-000000000001"), "00000000-0000-0000-0000-000000000001"),
])
def test_server_native_values_keep_existing_typed_formatting(value, expected):
    assert csv_text(value) == expected
