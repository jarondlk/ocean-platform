"""CLI inspection must not trigger local batch processing."""
from __future__ import annotations

import importlib
import sys

import pytest


@pytest.mark.parametrize("script", ["build_retrieval_docs", "run_pre_analysis", "run_reliability"])
@pytest.mark.parametrize("argument,exit_code", [("--help", 0), ("--unsupported-audit-argument", 2)])
def test_cli_inspection_never_starts_batch(monkeypatch, script, argument, exit_code):
    module = importlib.import_module(f"scripts.{script}")

    def forbidden(*_args, **_kwargs):
        pytest.fail("CLI help or invalid arguments started batch processing")

    monkeypatch.setattr(module.config, "ensure_dirs", forbidden)
    if hasattr(module, "run_all"):
        monkeypatch.setattr(module, "run_all", forbidden)
    monkeypatch.setattr(sys, "argv", [f"{script}.py", argument])
    with pytest.raises(SystemExit) as result:
        module.main()
    assert result.value.code == exit_code
