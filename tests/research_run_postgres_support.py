"""C20 acceptance on an explicitly identified disposable PostgreSQL database.

Only C20_TEST_DATABASE_URL is accepted. Each test owns a random schema, checks
the observed server before creating anything, and verifies its schema is gone.
The separate Alembic process receives only that validated database target.
"""
from __future__ import annotations

import ipaddress
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError



pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_INTEGRATION") != "1",
    reason="requires explicitly verified disposable C20 PostgreSQL",
)

ROOT = Path(__file__).resolve().parents[1]


def allowed_disposable_server_address(address):
    """Require loopback, or the exact workflow-owned RFC1918 IPv4 peer."""
    try:
        observed = ipaddress.ip_address(address or "")
    except ValueError:
        return False
    if observed.is_loopback:
        return True
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return False
    try:
        pinned = ipaddress.ip_address(os.environ.get("C20_TEST_SERVER_ADDRESS", ""))
    except ValueError:
        return False
    return observed == pinned and any(observed in ipaddress.ip_network(network) for network in (
        "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
    ))


def configured_disposable_url():
    raw = os.environ.get("C20_TEST_DATABASE_URL")
    if not raw:
        raise ValueError("C20_TEST_DATABASE_URL is required; DATABASE_URL is never used")
    try:
        url = make_url(raw)
    except ArgumentError as error:
        raise ValueError("C20_TEST_DATABASE_URL must be a PostgreSQL URL") from error
    if (
        url.get_backend_name() != "postgresql"
        or url.host not in {"127.0.0.1", "localhost", "::1"}
        or not re.fullmatch(r"ocean_c20_[a-z0-9_]+", url.database or "")
        or url.query
    ):
        raise ValueError("C20 URL must identify a dedicated ocean_c20_* loopback PostgreSQL database without query overrides")
    return url


@pytest.fixture(scope="module")
def disposable_database():
    try:
        url = configured_disposable_url()
    except ValueError as error:
        pytest.fail(str(error))
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            identity = connection.execute(text(
                "SELECT current_database(), host(inet_server_addr()), inet_server_port(), "
                "current_setting('server_version'), current_setting('transaction_isolation')"
            )).one()
            assert identity[0] == url.database
            assert allowed_disposable_server_address(identity[1]), "Observed server is not the verified disposable C20 server"
            assert identity[4] == "read committed"
        print(f"C20 disposable PostgreSQL identity: database={identity[0]} address={identity[1]} port={identity[2]} version={identity[3]} isolation={identity[4]}")
        yield engine, url
    finally:
        engine.dispose()


@pytest.fixture
def isolated(disposable_database):
    observer, url = disposable_database
    schema = f"c20_{uuid.uuid4().hex}"
    with observer.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    options = f"-csearch_path={schema} -clock_timeout=8000 -cstatement_timeout=20000"
    engine = create_engine(url, pool_pre_ping=True, connect_args={"options": options})
    bundle = {"engine": engine, "observer": observer, "schema": schema, "url": url, "options": options}
    try:
        yield bundle
    finally:
        engine.dispose()
        with observer.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            remaining = connection.scalar(text("SELECT count(*) FROM pg_namespace WHERE nspname=:schema"), {"schema": schema})
            assert remaining == 0
        print(f"C20 disposable schema cleanup: {schema} remaining=0")


def alembic(database, action, target, *, succeeds=True):
    # The parent has already verified the dedicated target's actual identity.
    # Replace the child's application URL explicitly; never inherit an app URL.
    child = dict(os.environ)
    child.update(
        DATABASE_URL=database["url"].update_query_dict({"options": database["options"]}).render_as_string(hide_password=False),
        AUTH_MODE="disabled", DEPLOYMENT_ENV="test", ENABLE_MOCK_LOGIN="false",
        PERSIST_LOCAL_CHAT="false",
    )
    result = subprocess.run(
        [sys.executable, "-m", "alembic", action, target], cwd=ROOT, env=child,
        capture_output=True, text=True, timeout=90, check=False,
    )
    if succeeds:
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0, "Populated downgrade unexpectedly succeeded"
    print(f"C20 Alembic {action} {target}: exit={result.returncode} schema={database['schema']}")
    return result


def revision(database):
    with database["engine"].connect() as connection:
        return connection.scalar(text("SELECT version_num FROM alembic_version"))


