"""Own, identify, exercise and stop a fresh loopback C21 PostgreSQL cluster.

No existing database URL is read. The default output files are exclusive;
intentional reruns must choose a new --output-subdir rather than replace them.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
import uuid

from sqlalchemy import create_engine, text


EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parents[4]
BINARIES = Path("/opt/homebrew/opt/postgresql@18/bin")
TEST_FILES = ("tests/integration/test_research_evidence_postgres.py",)
SOURCE_FILES = (
    "db/app_models.py", "orchestration/investigations.py",
    "migrations/versions/20261019_0019_research_evidence.py",
    "orchestration/research_evidence.py", "orchestration/research_evidence_projection.py",
    "orchestration/research_answers.py", "orchestration/research_synthesis.py", "orchestration/frozen_documentary.py",
    "orchestration/research_runs.py", "orchestration/research_controller.py", "orchestration/research_controller_scope.py",
    "orchestration/research_controller_observations.py", "schema/research_controller.py", "model_runtime.py", "config.py", "api/auth.py",
    "schema/research_evidence.py", "orchestration/catalogue_service.py",
    "tests/research_evidence_support.py", "tests/research_evidence_postgres_support.py", "tests/test_research_answers.py",
    *TEST_FILES, "docs/plans/ocean-v1/evidence/C21/store_verify_postgres.py",
)


def source_hashes():
    return {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        if (ROOT / name).is_file() else None
        for name in SOURCE_FILES
    }


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-subdir", help="New C21 evidence subdirectory for an intentional additional run")
    arguments = parser.parse_args()
    output = EVIDENCE
    if arguments.output_subdir:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", arguments.output_subdir):
            parser.error("--output-subdir must be one lowercase directory name")
        output = EVIDENCE / arguments.output_subdir
        output.mkdir(exist_ok=False)
    names = ("postgres-lifecycle.txt", "postgres-tests.txt", "postgres-result.json", "postgres-tested-source.json")
    if any((output / name).exists() for name in names):
        parser.error("Existing C21 receipts are immutable; select a new --output-subdir")
    missing_binaries = [name for name in ("initdb", "pg_ctl", "createdb") if not (BINARIES / name).is_file()]
    if missing_binaries:
        parser.error(f"Missing native PostgreSQL binaries: {missing_binaries}")
    before = source_hashes()
    missing_sources = [name for name, digest in before.items() if digest is None]
    if missing_sources:
        parser.error(f"Required implementation/test sources are not ready: {missing_sources}")
    cluster = Path(tempfile.mkdtemp(prefix="ocean-c21-postgres-", dir="/private/tmp"))
    data = cluster / "data"
    role = "ocean_c17"
    database = "ocean_c21_" + uuid.uuid4().hex
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    url = f"postgresql://{role}@127.0.0.1:{port}/{database}"
    result = {
        "component": "C21", "started_at": utc_now(),
        "cluster_root": str(cluster), "data_directory": str(data),
        "host": "127.0.0.1", "port": port, "role": role, "database": database,
        "existing_database_urls_used": False,
        "source_before_sha256": before,
    }
    code = 1
    # Native tools must not pick up PGHOST/PGSERVICE/PGOPTIONS or ambient URLs.
    native_environment = {
        key: value for key, value in os.environ.items()
        if not key.startswith("PG") and key != "DATABASE_URL"
        and not re.fullmatch(r"C\d+_TEST_DATABASE_URL", key)
    }
    with (output / "postgres-lifecycle.txt").open("x") as lifecycle:
        def run(command):
            return subprocess.run(
                [str(item) for item in command], cwd=ROOT, env=native_environment,
                stdout=lifecycle, stderr=subprocess.STDOUT, timeout=90, check=True,
            )

        def inspect_schemas():
            remaining = {}
            for target in (database,):
                engine = create_engine(f"postgresql://{role}@127.0.0.1:{port}/{target}", connect_args={"connect_timeout": 5})
                try:
                    with engine.connect() as connection:
                        remaining[target] = list(connection.scalars(text(
                            "SELECT nspname FROM pg_namespace WHERE nspname NOT IN "
                            "('information_schema','public') AND nspname NOT LIKE 'pg_%' ORDER BY nspname"
                        )))
                finally:
                    engine.dispose()
            result["remaining_test_schemas"] = remaining
            result["test_schemas_remaining"] = sum(len(items) for items in remaining.values())
            assert not result["test_schemas_remaining"], f"Disposable test schemas remain: {remaining}"

        try:
            run([BINARIES / "initdb", "-D", data, "-U", role, "--auth=trust", "--no-locale", "--encoding=UTF8"])
            run([BINARIES / "pg_ctl", "-D", data, "-l", cluster / "server.log", "-o",
                 f"-h 127.0.0.1 -p {port} -k {cluster}", "-w", "start"])
            run([BINARIES / "createdb", "-h", "127.0.0.1", "-p", port, "-U", role, database])
            engine = create_engine(url, connect_args={"connect_timeout": 5})
            try:
                with engine.connect() as connection:
                    row = connection.execute(text(
                        "SELECT current_database(),current_user,host(inet_server_addr()),inet_server_port(),"
                        "version(),current_setting('transaction_isolation'),current_setting('data_directory')"
                    )).one()
                    assert row[0] == database and row[1] == role
                    assert row[2] == "127.0.0.1" and row[3] == port
                    assert row[5] == "read committed" and Path(row[6]).resolve() == data.resolve()
                    result["identity"] = dict(zip(
                        ("database", "role", "host", "port", "version", "isolation", "data_directory"),
                        row, strict=True,
                    ))
                    assert row[4].startswith("PostgreSQL 18."), row[4]
            finally:
                engine.dispose()
            environment = dict(native_environment)
            environment.update(
                RUN_POSTGRES_INTEGRATION="1", C21_TEST_DATABASE_URL=url,
                DATABASE_URL="postgresql://unused:unused@127.0.0.1:1/c21_unused",
                AUTH_MODE="disabled", DEPLOYMENT_ENV="test", ENABLE_MOCK_LOGIN="false",
                PERSIST_LOCAL_CHAT="false", ENABLE_V1_INVESTIGATIONS="true",
                MODEL_PROVIDER="ollama", OLLAMA_BASE_URL="http://127.0.0.1:1",
                PY_COLORS="0",
            )
            for key in tuple(environment):
                if key == "GITHUB_ACTIONS" or re.fullmatch(r"C\d+_TEST_SERVER_ADDRESS", key):
                    environment.pop(key)
            command = [sys.executable, "-m", "pytest", *TEST_FILES, "-q", "-s", "--tb=short"]
            result["test_command"] = command
            started = time.monotonic()
            with (output / "postgres-tests.txt").open("x") as log:
                completed = subprocess.run(
                    command, cwd=ROOT, env=environment, stdout=log,
                    stderr=subprocess.STDOUT, timeout=600, check=False,
                )
            result["test_seconds"] = round(time.monotonic() - started, 3)
            result["test_exit_code"] = completed.returncode
            code = completed.returncode
            log_text = (output / "postgres-tests.txt").read_text()
            summaries = [line for line in log_text.splitlines() if re.search(r"\d+ passed", line)]
            result["test_summary"] = summaries[-1] if summaries else None
            counts = re.findall(r"(\d+) (passed|failed|skipped|errors|error)", result["test_summary"] or "")
            result["test_counts"] = {kind: int(amount) for amount, kind in counts}
            if not result["test_counts"].get("passed") or any(result["test_counts"].get(kind, 0) for kind in ("failed", "skipped", "error", "errors")):
                code = 1
        except BaseException as error:
            result["error"] = f"{type(error).__name__}: {error}"
            code = 1
        finally:
            if result.get("identity"):
                try:
                    inspect_schemas()
                except BaseException as error:
                    result["schema_cleanup_error"] = f"{type(error).__name__}: {error}"
                    code = 1
            # Stop by this invocation's fresh owned data directory only. No
            # process search, shared port kill, existing cluster or app URL.
            if (data / "postmaster.pid").exists():
                try:
                    stopped = subprocess.run(
                        [str(BINARIES / "pg_ctl"), "-D", str(data), "-m", "fast", "-w", "stop"],
                        cwd=ROOT, env=native_environment, stdout=lifecycle,
                        stderr=subprocess.STDOUT, timeout=90, check=False,
                    )
                    result["stop_exit_code"] = stopped.returncode
                except BaseException as error:
                    result["stop_error"] = f"{type(error).__name__}: {error}"
                    code = 1
            result["server_stopped"] = not (data / "postmaster.pid").exists()
            if not result["server_stopped"]:
                code = 1
            after = source_hashes()
            changed = [name for name in SOURCE_FILES if before[name] != after[name]]
            result["source_after_sha256"] = after
            result["source_changed_during_run"] = changed
            result["tested_source_unchanged"] = not changed
            if changed:
                code = 1
            result["finished_at"] = utc_now()
            result["driver_exit_code"] = code
            with (output / "postgres-tested-source.json").open("x") as stream:
                json.dump({"before_sha256": before, "after_sha256": after, "changed": changed}, stream, indent=2, sort_keys=True)
                stream.write("\n")
            lifecycle.flush()
            result["evidence_sha256"] = {
                name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                for name in ("postgres-lifecycle.txt", "postgres-tests.txt", "postgres-tested-source.json") if (output / name).is_file()
            }
            with (output / "postgres-result.json").open("x") as stream:
                json.dump(result, stream, indent=2, sort_keys=True)
                stream.write("\n")
    print(json.dumps({key: result.get(key) for key in (
        "driver_exit_code", "test_exit_code", "test_summary", "test_schemas_remaining",
        "server_stopped", "source_changed_during_run", "error",
    )}))
    return code


if __name__ == "__main__":
    sys.exit(main())
