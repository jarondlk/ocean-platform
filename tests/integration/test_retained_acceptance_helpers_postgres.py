"""New harness SQL helpers on exact restricted LOGINs; no Linux or guest code."""

from dataclasses import asdict
import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from orchestration.experiment_sandbox.contracts import SandboxError
from orchestration.research_experiments import ResearchExperimentError
from sandbox.experiment.gcp import run_retained_acceptance as module
from tests import experiment_execution_postgres_support as pg
from tests.integration import test_retained_admission_postgres as accepted
from tests.integration import test_retained_reserve_postgres as reserved

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_C23_POSTGRES_INTEGRATION") != "1",
    reason="Explicit owned disposable PostgreSQL required; starts no server",
)
disposable_database, isolated, role_database = (
    pg.disposable_database,
    pg.isolated,
    pg.role_database,
)
retained, case = reserved.retained, accepted.case


def configuration(case):
    database = case.native.database
    return {
        "database_name": database["url"].database,
        "schema": database["schema"],
        "roles": asdict(database["roles"]),
        "application_dsn": database["role_engines"][
            database["roles"].serving_role
        ].url.render_as_string(hide_password=False),
    }


def test_separate_application_observer_reads_c22_without_controller_grant_expansion(
    case,
):
    config = configuration(case)
    with case.hold() as context:
        accepted.start(case, context)
        accepted.finish(case, context)
        observed = module._c22_observation(config, case.identity)
        assert observed["fake_outbox_count"] == 0
        assert observed["reservation"]["id"] == case.identity.document["reservation_id"]
        assert observed["C22_observer_boundary"]["C23_write_privilege"] is False
    for table in ("research_experiment_reservation", "research_experiment_outbox"):
        with (
            pytest.raises(DBAPIError),
            case.native.database["controller_factory"]() as session,
        ):
            session.execute(text("SELECT * FROM " + table))


def test_actual_suspended_owner_after_terminal_denies_publication_with_feature_true(
    case,
):
    config = configuration(case)
    with case.hold() as context:
        accepted.start(case, context)
        terminal, outputs, _, _ = accepted.finish(case, context)
        observed = module._revoke_owner(config, case.native.fixture.user.id)
        assert observed["feature_flag_enabled"] is True
        assert (
            observed["readback_status"]
            == observed["observation"]["status"]
            == "suspended"
        )
        assert observed["observation"]["owner_user_id"] == str(
            case.native.fixture.user.id
        )
        assert (
            observed["observation"]["application_role"]
            == config["roles"]["serving_role"]
        )
        assert observed["observation"]["database_observed_at"]
        assert case.native.fixture.state["enabled"] is True
        import hashlib

        with pytest.raises((ResearchExperimentError, SandboxError)):
            case.hooks.admit_publication(
                context, terminal, hashlib.sha256(outputs.manifest_bytes).hexdigest()
            )
        assert case.hooks.close_execution(context, terminal).closed_fence == 3
