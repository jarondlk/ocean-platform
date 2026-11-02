"""Verify captured public JPY prices and arithmetic without network/credentials."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parent


def verify():
    manifest = json.loads((DIRECTORY / "artifacts.json").read_text())
    assert manifest["version"] == "beta-public-jpy-quote-artifacts-v1"
    for name, expected in manifest["sha256"].items():
        path = DIRECTORY / name
        assert path.parent.resolve() == DIRECTORY and path.is_file()
        assert not path.is_symlink()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name
    spec = importlib.util.spec_from_file_location(
        "beta_quote_arithmetic", DIRECTORY / "build_quote.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    selected, estimate = module.make()
    assert json.loads((DIRECTORY / "selected-prices.json").read_text()) == selected
    assert json.loads((DIRECTORY / "cost-qualification.json").read_text()) == estimate
    assert len(selected["selection"]) == len(selected["official_records"]) == 28
    assert not estimate["paid_resource_provisioning_performed"]
    assert not estimate["is_provider_hard_cap"]
    return {
        "verified": True,
        "selected_public_jpy_skus": len(selected["selection"]),
        "captured_artifacts_verified": len(manifest["sha256"]),
        "cost_730h_with_10_percent_contingency_jpy": estimate["scenario_730h"][
            "total_with_contingency_jpy"
        ],
        "cost_744h_with_10_percent_contingency_jpy": estimate["scenario_31day_744h"][
            "total_with_contingency_jpy"
        ],
        "headroom_under_50000_for_744h_jpy": estimate["scenario_31day_744h"][
            "headroom_to_50000_jpy"
        ],
        "free_credit_assumption": 0,
        "is_live_capacity_or_release_acceptance": False,
        "paid_provisioning_performed": False,
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
