"""Disposable native PostgreSQL context grants and restricted C17 transactions.

Native PostgreSQL18.3/pgvector0.8.7 qualification, not CloudSQL16 or real GCS.
All account/context inputs are synthetic and all cluster credentials stay private.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
from unittest.mock import patch
import uuid

from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[6]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
BIN = Path("/opt/homebrew/opt/postgresql@18/bin")
VECTOR = Path("/opt/homebrew/Cellar/pgvector/0.8.7")


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-directory", required=True)
    args = parser.parse_args()
    if not args.run_directory.replace("-", "").isalnum():
        parser.error("New simple owned run name required")
    output = HERE / args.run_directory
    output.mkdir(exist_ok=False)
    owned = Path(tempfile.mkdtemp(prefix="ocean-beta-context-pg-", dir="/private/tmp"))
    cluster, unix = owned / "pg", owned / "socket"
    unix.mkdir()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    report = {"version": "beta-context-native-v1", "state": "failed", "checks": [], "commands": [],
        "native_version": "PostgreSQL18.3/pgvector0.8.7, not CloudSQL16", "cloud_calls": False,
        "scientific_data": False, "private_owned_directory": str(owned)}
    engines, passwords = [], []
    started = False
    stage = "initialization"

    def check(name, value):
        report["checks"].append({"name": name, "passed": bool(value)})
        if not value:
            raise AssertionError(name)

    def command(name, argv, expected=0):
        result = subprocess.run(argv, capture_output=True, text=True, timeout=90)
        (output / (name + ".stdout")).write_text(result.stdout)
        (output / (name + ".stderr")).write_text(result.stderr)
        report["commands"].append({"name": name, "returncode": result.returncode, "expected": expected})
        if result.returncode != expected:
            raise AssertionError(name)

    try:
        base = module("context_native_base", ROOT / "deploy/gcp/beta/operator/operator.py")
        operator = module("context_native_grants", ROOT / "deploy/gcp/beta/context-operator/context_operator.py")
        context = module("context_native_api_package", ROOT / "deploy/gcp/beta/api/prepare_context.py")
        password = secrets.token_urlsafe(48)
        passwords.append(password)
        pwfile = owned / "init-password"
        pwfile.write_text(password + "\n")
        pwfile.chmod(0o600)
        command("initdb", [str(BIN / "initdb"), "-D", str(cluster), "--username=postgres", "--auth-local=trust",
            "--auth-host=scram-sha-256", "--pwfile=" + str(pwfile), "--no-locale"])
        pwfile.unlink()
        extension = owned / "extension"
        extension.mkdir()
        for source in (VECTOR / "share/postgresql@18/extension").glob("vector*"):
            shutil.copyfile(source, extension / source.name)
        control = extension / "vector.control"
        control.write_text(control.read_text().replace("'$libdir/vector'", repr(str(VECTOR / "lib/postgresql@18/vector"))))
        with (cluster / "postgresql.conf").open("a") as handle:
            handle.write("\nextension_control_path = '" + str(extension) + ":$system'\n")
            for name, value in base.PASSWORD_LOGGING_POLICY.items():
                handle.write(name + " = '" + value + "'\n")
        command("pg-start", [str(BIN / "pg_ctl"), "-D", str(cluster), "-l", str(owned / "postgres.log"),
            "-o", f"-h 127.0.0.1 -p {port} -k {unix}", "-w", "start"])
        started = True
        admin_url = URL.create("postgresql+psycopg2", username="postgres", password=password,
            host="127.0.0.1", port=port, database="postgres")
        admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", hide_parameters=True)
        engines.append(admin)
        with admin.connect() as connection:
            connection.exec_driver_sql("CREATE DATABASE ocean_v1_beta OWNER postgres")
        postgres_url = admin_url.set(database=operator.DATABASE)
        postgres = create_engine(postgres_url, hide_parameters=True)
        engines.append(postgres)
        env = {key: value for key, value in os.environ.items() if key != "DATABASE_URL"}
        env.update(DEPLOYMENT_ENV="production", OCEAN_V1_PROJECT_ID=base.PROJECT,
            OCEAN_V1_SQL_CONNECTION_NAME=base.CONNECTION,
            OCEAN_V1_MIGRATOR_PASSWORD=secrets.token_urlsafe(48), OCEAN_V1_SERVING_PASSWORD=secrets.token_urlsafe(48))
        for name in base.FLAGS:
            env[name] = "false"
        passwords.extend([env["OCEAN_V1_MIGRATOR_PASSWORD"], env["OCEAN_V1_SERVING_PASSWORD"]])
        stage = "restricted-bootstrap"
        with postgres.begin() as connection:
            bootstrap = base.bootstrap(connection, env)
        check("native bootstrap vector and restricted roles", bootstrap["extension"]["version"] == "0.8.7")
        migrator_url = postgres_url.set(username=base.MIGRATOR, password=env["OCEAN_V1_MIGRATOR_PASSWORD"])
        serving_url = postgres_url.set(username=base.SERVING, password=env["OCEAN_V1_SERVING_PASSWORD"])
        migrator, serving = [create_engine(url, hide_parameters=True) for url in (migrator_url, serving_url)]
        engines.extend([migrator, serving])
        application = owned / "application"
        for source in context.selected_sources():
            destination = application / source.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        shutil.copyfile(ROOT / "deploy/gcp/beta/api/entry.py", application / "beta_entry.py")
        stage = "migration"
        with patch.object(base, "ROOT", application):
            migrated = base.run_stage("migrate", {"dsn": migrator_url.render_as_string(hide_password=False), "user": base.MIGRATOR}, env)
        check("restricted native migration reaches exact0021", migrated["readback"]["migration_versions"] == [base.HEAD])
        with migrator.begin() as connection:
            base.finalize(connection)
        check("existing auth limiter grants accepted before context extension", True)
        os.environ["DEPLOYMENT_ENV"] = "test"
        os.environ["ENABLE_V1_INVESTIGATIONS"] = "true"
        os.environ["ENABLE_V1_CATALOGUE"] = "true"
        os.environ["ENABLE_V1_CATALOGUE_BROWSER"] = "true"
        from api.auth import current_user_from_model
        from api.v1_beta_research_host import SITE_ID, compose_beta_context_services
        from api.v1_catalogue_host import load_snapshot_catalogue
        from db.app_models import AppUser
        from ingestion.artifact_store import BoundedLocalStore
        from orchestration.investigations import InvestigationError
        from tests.test_beta_snapshot_catalogue import PREPARE, RAW
        factory = sessionmaker(bind=serving, expire_on_commit=False)
        with sessionmaker(bind=migrator).begin() as session:
            user = AppUser(id=uuid.uuid4(), auth_provider="google", auth_subject="native-context-synthetic-user",
                email="native-context@beta.invalid", display_name="Synthetic context owner", role="admin",
                account_type="internal", status="active")
            session.add(user)
            session.flush()
            actor = current_user_from_model(user)
        sealed = owned / "sealed"
        sealed.mkdir(mode=0o700)
        plan = PREPARE.planned_snapshots(RAW, source_sha256=hashlib.sha256(RAW).hexdigest())
        result = PREPARE.seal_catalogue(sealed, plan)
        activation = sealed / "store" / result["activation_object_key"]
        activation.parent.mkdir(parents=True)
        activation.write_bytes((sealed / "activation.json").read_bytes())
        binding = {"version": "ocean-v1-gcs-catalogue-host-v1", "project_id": base.PROJECT, "site_id": SITE_ID,
            "bucket": base.PROJECT + "-snapshots", "prefix": "v1/catalogue",
            "activation_object": result["activation_object_key"], "activation_sha256": result["activation_sha256"]}
        source = owned / "catalogue-binding.json"
        source.write_bytes(PREPARE.canonical(binding))
        source.chmod(0o444)
        catalogue, browser = load_snapshot_catalogue(source, project_id=base.PROJECT, site_id=SITE_ID,
            cursor_key=b"native-synthetic-catalogue-key" * 2, context_retention=True,
            _allow_test_owner=True, _test_store=BoundedLocalStore(sealed / "store"))
        services = compose_beta_context_services(session_factory=factory, site_id=SITE_ID,
            catalogue_service=catalogue, catalogue_browser=browser)
        payload = {"name": "Synthetic native context", "snapshot_id": plan["index_id"],
            "scope": PREPARE.scope().model_dump(mode="json"), "idempotency_key": str(uuid.uuid4())}
        # Deliberately rehearse the initially proposed non-audit-read grants to
        # prove the actual ORM requirement before accepting the final policy.
        stage = "audit-returning-probe"
        with migrator.begin() as connection:
            for table, privileges in operator.CONTEXT_TABLE_PRIVILEGES.items():
                for privilege in privileges:
                    base.statement(connection, "GRANT " + privilege + " ON TABLE public.{} TO {}", table, base.SERVING)
            for table, kinds in operator.CONTEXT_COLUMN_PRIVILEGES.items():
                for privilege, columns in kinds.items():
                    if table == "audit_event":
                        continue
                    for column in columns:
                        base.statement(connection, "GRANT " + privilege + " ({}) ON TABLE public.{} TO {}", column, table, base.SERVING)
        failures = []
        @event.listens_for(serving, "handle_error")
        def capture(context):
            statement = context.statement or ""
            failures.append({"sqlstate": getattr(context.original_exception, "pgcode", None),
                "audit_insert": "INSERT INTO audit_event" in statement,
                "returning_created_at": "RETURNING audit_event.created_at" in statement})
        try:
            services.investigation_service.invoke("create", payload, actor)
        except InvestigationError as error:
            check("without audit created_at SELECT actual C17 preparation is rejected", error.code == "operation_pending")
        else:
            raise AssertionError("Missing audit RETURNING privilege unexpectedly succeeded")
        check("actual ORM audit INSERT RETURNING created_at requires column SELECT", any(
            row["sqlstate"] == "42501" and row["audit_insert"] and row["returning_created_at"] for row in failures))
        report["initial_audit_returning_probe"] = failures
        event.remove(serving, "handle_error", capture)
        stage = "context-grants"
        with migrator.begin() as connection:
            applied = operator.apply_context_grants(connection, base, _allow_test_postgres=True)
        check("exact context table-column policy succeeds as restricted migrator", applied["effective_privileges_verified"])
        with migrator.connect() as connection:
            operator.verify_privileges(connection, require_complete=True)
        check("fresh connection verifies exact effective rights", True)
        stage = "actual-c17-transactions"
        created = services.investigation_service.invoke("create", payload, actor)
        identity = created["investigation"]["id"]
        check("actual restricted serving C17 create succeeds", created["operation"]["state"] == "committed")
        repeated = services.investigation_service.invoke("create", payload, actor)
        check("actual C17 idempotent replay returns same immutable revision", repeated["context"]["id"] == created["context"]["id"])
        chat = services.investigation_service.invoke("conversations/create", {"investigation_id": identity,
            "name": "Synthetic native chat", "idempotency_key": str(uuid.uuid4())}, actor)
        renamed = services.investigation_service.invoke("conversations/rename", {"investigation_id": identity,
            "conversation_id": chat["conversation"]["id"], "name": "Renamed native chat",
            "expected_version": chat["conversation"]["metadata_version"], "idempotency_key": str(uuid.uuid4())}, actor)
        check("actual conversation create and versioned rename succeed", renamed["conversation"]["name"] == "Renamed native chat")
        attached = services.investigation_service.invoke("context/change", {"investigation_id": identity,
            "expected_revision_id": created["context"]["id"], "idempotency_key": str(uuid.uuid4()), "change": {"op": "attach",
                "reference": {"kind": "catalogue", "id": plan["dataset"].dataset_id, "snapshot_id": plan["index_id"]}}}, actor)
        check("actual immutable context revision and catalogue attachment succeed", len(attached["context"]["attachments"]) == 1)
        renamed = services.investigation_service.invoke("rename", {"investigation_id": identity, "name": "Renamed native context",
            "expected_version": attached["investigation"]["metadata_version"], "idempotency_key": str(uuid.uuid4())}, actor)
        archived = services.investigation_service.invoke("archive", {"investigation_id": identity, "archived": True,
            "expected_version": renamed["investigation"]["metadata_version"], "idempotency_key": str(uuid.uuid4())}, actor)
        check("actual investigation rename and archive succeed", archived["investigation"]["status"] == "archived")
        factory.close_all()
        reloaded = services.investigation_service.invoke("get", {"investigation_id": identity}, actor)
        check("fresh sessions retain immutable context and history", reloaded["context"]["id"] == attached["context"]["id"])
        stage = "least-privilege-denials"
        denied = {
            "account authority UPDATE denied": "UPDATE public.app_user SET role='viewer' WHERE false",
            "append-only revision UPDATE denied": "UPDATE public.research_context_revision SET payload_json=payload_json WHERE false",
            "context DELETE denied": "DELETE FROM public.research_investigation WHERE false",
            "unrelated retained run reads denied": "SELECT * FROM public.research_run LIMIT 0",
            "full audit reads denied": "SELECT * FROM public.audit_event LIMIT 0",
            "audit action column reads denied": "SELECT action FROM public.audit_event LIMIT 0",
            "serving DDL denied": "CREATE TABLE public.native_unexpected_context_object(id int)",
        }
        for name, statement in denied.items():
            try:
                with serving.begin() as connection:
                    connection.exec_driver_sql(statement)
            except DBAPIError as error:
                check(name, getattr(error.orig, "pgcode", None) == "42501")
            else:
                raise AssertionError(name)
        with serving.begin() as connection:
            connection.exec_driver_sql("SELECT created_at FROM public.audit_event LIMIT 0")
        check("audit created_at column alone is readable", True)
        stage = "unexpected-privilege-refusal"
        injections = [
            ("table UPDATE bypass", "GRANT UPDATE ON public.research_investigation TO ocean_v1_serving", "REVOKE UPDATE ON public.research_investigation FROM ocean_v1_serving"),
            ("forbidden account column", "GRANT UPDATE(role) ON public.app_user TO ocean_v1_serving", "REVOKE UPDATE(role) ON public.app_user FROM ocean_v1_serving"),
            ("audit private column", "GRANT SELECT(metadata_json) ON public.audit_event TO ocean_v1_serving", "REVOKE SELECT(metadata_json) ON public.audit_event FROM ocean_v1_serving"),
            ("allowed column delegation", "GRANT SELECT(created_at) ON public.audit_event TO ocean_v1_serving WITH GRANT OPTION", "REVOKE GRANT OPTION FOR SELECT(created_at) ON public.audit_event FROM ocean_v1_serving"),
            ("PUBLIC history ACL", "GRANT SELECT ON public.chat_interaction TO PUBLIC", "REVOKE SELECT ON public.chat_interaction FROM PUBLIC"),
        ]
        for name, inject, restore in injections:
            with migrator.begin() as connection:
                connection.exec_driver_sql(inject)
            try:
                with migrator.begin() as connection:
                    operator.apply_context_grants(connection, base, _allow_test_postgres=True)
            except operator.ContextOperatorError:
                check("unexpected " + name + " is refused without automatic reset", True)
            else:
                raise AssertionError(name)
            with migrator.begin() as connection:
                connection.exec_driver_sql(restore)
        with migrator.begin() as connection:
            operator.apply_context_grants(connection, base, _allow_test_postgres=True)
        check("idempotent grants pass after restoring only injected native conditions", True)
        report["grant_result"] = applied
        report["state"] = "passed"
    except Exception as error:
        report.update(failure_type=type(error).__name__, failure_stage=stage)
    finally:
        for engine in engines:
            engine.dispose()
        if started:
            command("pg-stop", [str(BIN / "pg_ctl"), "-D", str(cluster), "-m", "immediate", "-w", "stop"])
            command("pg-stopped", [str(BIN / "pg_ctl"), "-D", str(cluster), "status"], expected=3)
        with socket.socket() as sock:
            closed = sock.connect_ex(("127.0.0.1", port)) != 0
        report["cleanup"] = {"port_closed": closed, "postmaster_pid_absent": not (cluster / "postmaster.pid").exists()}
        logfile = owned / "postgres.log"
        if logfile.exists():
            data = logfile.read_bytes()
            check("private cluster log contains no generated plaintext credentials", all(value.encode() not in data for value in passwords))
            report["private_log"] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "copied_to_repository": False}
        shutil.rmtree(owned)
        report["cleanup"]["private_directory_removed"] = not owned.exists()
        paths = [ROOT / "deploy/gcp/beta/context-operator/context_operator.py", Path(__file__).resolve(),
            ROOT / "api/v1_beta_research_host.py", ROOT / "ingestion/beta_catalogue_retention.py"]
        report["source_pins"] = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
        report["artifacts"] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in output.iterdir() if path.is_file()}
        (output / "receipt.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "checks": len(report["checks"]), "failure_stage": report.get("failure_stage"), "cleanup": report["cleanup"]}))
    return 0 if report["state"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
