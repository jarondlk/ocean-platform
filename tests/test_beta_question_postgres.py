"""Disposable PostgreSQL16 role rehearsal; accepts only the build container.

Actual migrations and SQL guards run. Scientific inputs and cloud delivery are
synthetic; this does not establish Cloud SQL, real GCS or model acceptance.
"""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from api.auth import current_user_from_model
from api.v1_beta_question_services import compose_beta_question_services
from api.v1_beta_research_host import SITE_ID, compose_beta_context_services, CONTEXT_TABLE_PRIVILEGES, CONTEXT_UPDATE_COLUMNS
from api.v1_catalogue_host import load_snapshot_catalogue
from api.v1_research_controller_host import create_controller_app
from db.app_models import AppUser
from ingestion.artifact_store import BoundedLocalStore
from tests import test_beta_question_services as journey
from tests.test_beta_question_services import questions as questions
from tests.test_beta_snapshot_catalogue import sealed as sealed
from tests.test_cloud_research_dispatch import Transport

ROOT = Path(__file__).resolve().parents[1]
NATIVE_URL = os.environ.get("OCEAN_BETA_RESEARCH_NATIVE_TEST_URL")
pytestmark = pytest.mark.skipif(not NATIVE_URL, reason="Explicit disposable PG16 qualification target required")


@pytest.fixture
def native(monkeypatch):
    url = make_url(NATIVE_URL)
    assert (url.drivername == "postgresql+psycopg2" and url.host == "pg-beta-research-qualification"
        and url.port == 5432 and url.database == "ocean_v1_beta" and url.username == "postgres"
        and not url.query and not url.password)
    admin = create_engine(url)
    migrator = url.set(username="ocean_v1_migrator")
    with admin.begin() as c:
        assert 160000 <= int(c.scalar(text("SHOW server_version_num"))) < 170000
        c.execute(text("CREATE EXTENSION vector"))
        for role in ("ocean_v1_migrator", "ocean_v1_serving"):
            c.exec_driver_sql(f'CREATE ROLE "{role}" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS')
        c.execute(text("ALTER DATABASE ocean_v1_beta OWNER TO ocean_v1_migrator"))
        c.execute(text("ALTER SCHEMA public OWNER TO ocean_v1_migrator"))
        c.execute(text("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
        c.execute(text("REVOKE CONNECT, TEMP ON DATABASE ocean_v1_beta FROM PUBLIC"))
    env = {**os.environ, "DATABASE_URL": migrator.render_as_string(hide_password=False), "DEPLOYMENT_ENV": "test"}
    for key in list(env):
        if key.startswith("ENABLE_V1_"):
            env[key] = "false"
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env,
        check=True, stdout=subprocess.DEVNULL)
    owner = create_engine(migrator)
    directory = ROOT / "deploy/gcp/beta/research-operator"
    def load(name, filename):
        spec = importlib.util.spec_from_file_location(name, directory / filename)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        return module
    load("privileges", "privileges.py")
    operator = load("native_research_operator", "research_operator.py")
    package = load("native_research_operator_package", "prepare_context.py")
    credential = load("native_controller_credential", "controller_credential.py")
    base = load("native_password_base", "../operator/operator.py")
    class MemorySecret:
        def __init__(self):
            self._dsn = None
            self.adds = 0
        def empty(self):
            return self._dsn is None
        def add(self, value):
            assert self.empty()
            self._dsn = value
            self.adds += 1
            return "1"
        def access(self, version):
            assert version == "1"
            return self._dsn
    secret = MemorySecret()
    with admin.begin() as c:
        c.execute(text("REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC"))
        version, controller_dsn = credential.initialize(c, store=secret, base=base)
        assert version == "1" and secret.adds == 1
    with pytest.raises(ValueError, match="refuses existing"), admin.begin() as c:
        credential.initialize(c, store=secret, base=base)
    with admin.begin() as c:
        same_version, same_dsn = credential.initialize(c, store=secret, base=base, version="1")
        assert same_version == version and same_dsn == controller_dsn and secret.adds == 1
    with owner.begin() as c:
        assert c.scalar(text("SELECT version_num FROM alembic_version")) == "20261027_0021"
        for table, rights in CONTEXT_TABLE_PRIVILEGES.items():
            c.exec_driver_sql('GRANT ' + ', '.join(sorted(rights)) + ' ON TABLE public."' + table + '" TO ocean_v1_serving')
        for table, columns in CONTEXT_UPDATE_COLUMNS.items():
            c.exec_driver_sql('GRANT UPDATE (' + ', '.join('"' + s + '"' for s in sorted(columns)) + ') ON TABLE public."' + table + '" TO ocean_v1_serving')
        c.execute(text("GRANT SELECT(created_at) ON public.audit_event TO ocean_v1_serving"))
        c.execute(text("GRANT SELECT, INSERT, UPDATE ON public.rate_limit_bucket TO ocean_v1_serving"))
        c.execute(text("GRANT CONNECT ON DATABASE ocean_v1_beta TO ocean_v1_serving"))
        operator.apply(c, package.schema_contract())
    # An uncertain outcome must be inspected; the operator cannot blindly replay
    # CREATE/GRANT or replace an existing security-definer function.
    with pytest.raises(ValueError, match="already exists"), owner.begin() as c:
        operator.apply(c, package.schema_contract())
    serving = create_engine(url.set(username="ocean_v1_serving"), pool_pre_ping=True)
    controller_url = make_url(controller_dsn).set(host=url.host)
    controller = create_engine(controller_url, pool_pre_ping=True, hide_parameters=True)
    # The qualification container's first HBA rule requires SCRAM for this role.
    bad = create_engine(controller_url.set(password="synthetic-wrong-password"), hide_parameters=True)
    with pytest.raises(DBAPIError):
        with bad.connect():
            pytest.fail("Wrong controller password must never authenticate")
    bad.dispose()
    owner_factory = sessionmaker(bind=owner, expire_on_commit=False)
    with owner_factory.begin() as s:
        actor = AppUser(id=uuid.uuid4(), auth_subject="subject-1", auth_provider="oidc", email="owner@beta.invalid",
            display_name="Synthetic native owner", role="admin", account_type="internal", status="active")
        s.add(actor)
    result = {"actor": current_user_from_model(actor), "serving": serving, "controller": controller,
        "factory": sessionmaker(bind=serving, expire_on_commit=False),
        "controller_factory": sessionmaker(bind=controller, expire_on_commit=False)}
    original = journey.private_app
    def private(questions, **claims):
        api = questions[0]
        worker = compose_beta_question_services(session_factory=result["controller_factory"],
            catalogue_service=api.catalogue_service, catalogue_browser=api.catalogue_browser,
            cloud_settings=api.cloud_settings, model_settings=api.model_settings)
        for service in (worker.research_run_service, worker.research_answer_service):
            service.queue._session = Transport()
        monkeypatch.setattr(worker.research_answer_service.runtime, "structured_chat_result",
            lambda **kw: pytest.fail("No live provider call in qualification"))
        return create_controller_app(settings=worker.cloud_settings, runs=worker.research_run_service,
            answers=worker.research_answer_service,
            token_verifier=lambda token, audience: journey.invoker(worker.cloud_settings, **claims))
    monkeypatch.setattr(journey, "private_app", private)
    yield result
    monkeypatch.setattr(journey, "private_app", original)
    for engine in (serving, controller, owner, admin):
        engine.dispose()


@pytest.fixture
def context(sealed, native):
    catalogue, browser = load_snapshot_catalogue(sealed[0], project_id="ocean-v1-beta-20261101", site_id=SITE_ID,
        cursor_key=b"synthetic-native-qualification-cursor" * 2, context_retention=True,
        _allow_test_owner=True, _test_store=BoundedLocalStore(sealed[1] / "store"))
    services = compose_beta_context_services(session_factory=native["factory"], site_id=SITE_ID,
        catalogue_service=catalogue, catalogue_browser=browser)
    return services, native["actor"], native["factory"], sealed


def test_pg16_roles_finish_question_and_reopen_answer_without_account_write_rights(questions, native):
    for engine in (native["serving"], native["controller"]):
        with engine.connect() as c:
            assert not c.scalar(text("SELECT has_any_column_privilege(current_user, 'public.app_user', 'UPDATE')"))
            assert not c.scalar(text("SELECT has_table_privilege(current_user, 'public.research_run', 'DELETE')"))
        with pytest.raises(DBAPIError), engine.begin() as c:
            c.execute(text("UPDATE public.app_user SET display_name='forbidden'"))
        with pytest.raises(DBAPIError), engine.begin() as c:
            c.execute(text("SELECT id FROM public.app_user FOR NO KEY UPDATE"))
        with engine.begin() as c:
            c.execute(text("SELECT public.ocean_v1_beta_research_owner_lock(:id)"), {"id": native["actor"].id})
    journey.test_question_is_durable_before_private_delivery_and_answer_reopens(questions)
