"""CLI behavior tests for the manual batch pipeline wrapper."""
from __future__ import annotations

from argparse import Namespace

from scripts.run_pipeline import _request_from_args


def _args(**overrides) -> Namespace:
    values = {
        "stages": "full",
        "validate_only": False,
        "execute": None,
        "tag": None,
        "skip_sst": False,
        "reset_db": False,
        "embed": True,
        "embedding_model": None,
        "embedding_batch_size": 32,
        "notes": None,
    }
    values.update(overrides)
    return Namespace(**values)


def test_validate_only_executes_safe_validation_by_default() -> None:
    request = _request_from_args(_args(validate_only=True))

    assert request.stages == ["validate_raw"]
    assert request.dry_run is False


def test_validate_only_respects_explicit_dry_run() -> None:
    request = _request_from_args(_args(validate_only=True, execute=False))

    assert request.stages == ["validate_raw"]
    assert request.dry_run is True


def test_full_pipeline_remains_dry_run_by_default() -> None:
    request = _request_from_args(_args())

    assert request.dry_run is True
