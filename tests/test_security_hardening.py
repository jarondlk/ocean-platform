from __future__ import annotations

import pandas as pd
import pytest

from api.auth import ROLE_PERMISSIONS, route_permission
from api.main import _allowed_model, _filter_explore_df
from fastapi import HTTPException


def test_model_allowlist_rejects_unconfigured_model():
    assert _allowed_model(
        "chat-approved",
        default="chat-default",
        allowed=frozenset({"chat-default", "chat-approved"}),
        label="chat model",
    ) == "chat-approved"

    with pytest.raises(HTTPException) as exc_info:
        _allowed_model(
            "attacker-selected-model",
            default="chat-default",
            allowed=frozenset({"chat-default"}),
            label="chat model",
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "model_not_allowed"


def test_explore_search_treats_regex_metacharacters_literally():
    frame = pd.DataFrame({"description": ["plain text", ".*", "other"]})

    filtered = _filter_explore_df(
        frame,
        {"date_columns": []},
        bay=None,
        station=None,
        source=None,
        time_from=None,
        time_to=None,
        search=".*",
    )

    assert filtered["description"].tolist() == [".*"]


def test_retention_route_is_admin_only():
    assert route_permission("PATCH", "/admin/retention/interactions/id/hold") == "retention:manage"
    assert "retention:manage" in ROLE_PERMISSIONS["admin"]
    assert "retention:manage" not in ROLE_PERMISSIONS["researcher"]
