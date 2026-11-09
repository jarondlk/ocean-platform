"""Pure entry/configuration checks; never acquire credentials or connect SQL."""
import json

import pytest

from api.v1_beta_question_entry import validate_environment
from api.v1_beta_question_services import load_question_configuration
from tests.test_cloud_research_dispatch import cloud_settings


def environment(role="api"):
    user = "ocean_v1_serving" if role == "api" else "ocean_v1_research_controller"
    return {"DEPLOYMENT_ENV": "production", "OCEAN_V1_PROJECT_ID": "ocean-v1-beta-20261101",
        "OCEAN_V1_CATALOGUE_MODE": "sealed-gcs-research-v1", "OCEAN_V1_DATABASE_USER": user,
        "OCEAN_V1_DATABASE_URL": "postgresql+psycopg2://" + user + ":synthetic-test-only@127.0.0.1:5432/ocean_v1_beta",
        "OCEAN_V1_SQL_CONNECTION_NAME": "ocean-v1-beta-20261101:asia-northeast1:ocean-v1-beta-sql",
        "OCEAN_V1_RESEARCH_CONFIG_JSON": json.dumps({"cloud": cloud_settings().model_dump(),
            "model": {"model": "gemini-3.8-flash", "location": "global", "max_output_tokens": 4096}})}


@pytest.mark.parametrize("role", ["api", "controller"])
def test_explicit_roles_validate_without_external_effects(role):
    assert validate_environment(environment(role), role) is None


@pytest.mark.parametrize("field,value", [
    ("DEPLOYMENT_ENV", "development"), ("OCEAN_V1_PROJECT_ID", "legacy-project"),
    ("DATABASE_URL", "ambient-target"), ("OCEAN_V1_CATALOGUE_MODE", "sealed-gcs-context-v1"),
    ("ENABLE_V1_EXPERIMENT_DISPATCH", "true"), ("ENABLE_V1_RESEARCH_CONTROLLER", "invalid"),
    ("OCEAN_V1_DATABASE_USER", "postgres"),
    ("OCEAN_V1_DATABASE_URL", "postgresql+psycopg2://ocean_v1_serving:synthetic@legacy.invalid:5432/ocean_v1_beta"),
    ("OCEAN_V1_SQL_CONNECTION_NAME", "legacy:asia-northeast1:sql"),
])
def test_wrong_targets_ambient_config_and_experiments_cannot_start_research(field, value):
    with pytest.raises(ValueError):
        validate_environment({**environment(), field: value}, "api")


def test_controller_cannot_reuse_serving_sql_identity():
    with pytest.raises(ValueError):
        validate_environment(environment("api"), "controller")


def test_configuration_has_exactly_one_bounded_explicit_source(tmp_path):
    raw = environment()["OCEAN_V1_RESEARCH_CONFIG_JSON"]
    path = tmp_path / "research.json"
    path.write_text(raw)
    assert load_question_configuration(str(path)) == load_question_configuration(document_json=raw)
    for kwargs in [{}, {"filename": str(path), "document_json": raw},
                   {"document_json": raw[:-1] + ',"api_key":"never-accepted"}'},
                   {"document_json": '{"cloud":{},"cloud":{},"model":{}}'}, {"document_json": "x" * 16385}]:
        with pytest.raises(ValueError):
            load_question_configuration(**kwargs)
