from types import SimpleNamespace
from unittest.mock import Mock

import api.main as api_main


def test_models_reports_expected_runtime_outage_without_exception_log(monkeypatch):
    runtime = SimpleNamespace(
        list_models=Mock(side_effect=ConnectionError("model runtime unavailable")),
    )
    warning = Mock()
    exception = Mock()
    monkeypatch.setattr(api_main, "get_model_runtime", lambda: runtime)
    monkeypatch.setattr(api_main.logger, "warning", warning)
    monkeypatch.setattr(api_main.logger, "exception", exception)

    response = api_main.models()

    assert response.available is False
    assert response.error == "Model discovery is unavailable"
    warning.assert_called_once()
    exception.assert_not_called()


def test_debug_state_treats_missing_dataset_as_expected(monkeypatch, tmp_path):
    missing_path = tmp_path / "missing.parquet"
    monkeypatch.setattr(
        api_main,
        "EXPLORE_DATASETS",
        {"missing": {"label": "Missing dataset", "path": missing_path}},
    )
    monkeypatch.setattr(api_main, "_debug_artifacts", lambda: {})
    monkeypatch.setattr(
        api_main,
        "health",
        lambda: SimpleNamespace(model_dump=lambda: {}),
    )
    monkeypatch.setattr(
        api_main,
        "stats",
        lambda: SimpleNamespace(model_dump=lambda: {}),
    )
    exception = Mock()
    monkeypatch.setattr(api_main.logger, "exception", exception)
    api_main._read_explore_dataset.cache_clear()

    payload = api_main.debug_state()

    assert payload["datasets"]["missing"] == {
        "label": "Missing dataset",
        "path": str(missing_path),
        "exists": False,
        "error": f"Dataset artifact is missing: {missing_path}",
    }
    exception.assert_not_called()
