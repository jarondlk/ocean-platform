"""Initialize only the beta controller SQL role and its existing empty secret.

Credentials exist only in job memory, the SQL SCRAM verifier and Secret Manager.
No automatic retry follows an uncertain secret/SQL result. Reconciliation must
explicitly select an already created numeric version; it never generates another
credential or replaces an unrelated role.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys

import google_crc32c
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url, URL

PROJECT = "ocean-v1-beta-20261101"
DATABASE = "ocean_v1_beta"
ROLE = "ocean_v1_research_controller"
SECRET = "projects/" + PROJECT + "/secrets/ocean-v1-beta-controller-database"
SECRET_ALIASES = (SECRET, "projects/534831104543/secrets/ocean-v1-beta-controller-database")
ROOT = Path(__file__).resolve().parent


class ControllerSecret:
    def __init__(self, session=None):
        self._session = session

    def request(self, method, suffix, **kwargs):
        try:
            if self._session is None:
                import google.auth
                from google.auth.transport.requests import AuthorizedSession
                credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
                self._session = AuthorizedSession(credentials)
            response = self._session.request(method, "https://secretmanager.googleapis.com/v1/" + SECRET + suffix,
                timeout=15, allow_redirects=False, **kwargs)
            if response.status_code != 200:
                raise ValueError()
            return response.json()
        except Exception:
            raise ValueError("Controller credential storage rejected or uncertain") from None

    def empty(self):
        result = self.request("GET", "/versions", params={"pageSize": 2})
        return not result.get("versions") and not result.get("nextPageToken")

    def add(self, dsn):
        raw = dsn.encode()
        result = self.request("POST", ":addVersion", json={"payload": {
            "data": base64.b64encode(raw).decode(), "dataCrc32c": str(google_crc32c.value(raw))}})
        name = result.get("name", "")
        if not any(re.fullmatch(re.escape(prefix) + r"/versions/[1-9][0-9]*", name) for prefix in SECRET_ALIASES):
            raise ValueError("Controller secret version outcome is uncertain")
        return name.rsplit("/", 1)[-1]

    def access(self, version):
        if type(version) is not str or re.fullmatch(r"[1-9][0-9]*", version) is None:
            raise ValueError("Explicit numeric controller credential version required")
        result = self.request("GET", "/versions/" + version + ":access")
        if result.get("name") not in {prefix + "/versions/" + version for prefix in SECRET_ALIASES}:
            raise ValueError("Exact controller secret version required")
        payload = result["payload"]
        raw = base64.b64decode(payload["data"], validate=True)
        if str(google_crc32c.value(raw)) != str(payload.get("dataCrc32c")):
            raise ValueError("Controller credential integrity check failed")
        return raw.decode()


def credential_url(raw):
    value = make_url(raw)
    if (value.drivername != "postgresql+psycopg2" or value.host != "127.0.0.1" or value.port != 5432
            or value.database != DATABASE or value.username != ROLE or value.query
            or not value.password or re.fullmatch(r"[A-Za-z0-9_-]{48,128}", value.password) is None):
        raise ValueError("Exact private controller credential required")
    return value


def initialize(connection, *, store, base, version=None):
    if connection.dialect.name != "postgresql" or tuple(connection.execute(text("SELECT current_database(),current_user")).one()) != (DATABASE, "postgres"):
        raise ValueError("Exact beta credential bootstrap identity required")
    if not 160000 <= int(connection.scalar(text("SHOW server_version_num"))) < 170000:
        raise ValueError("Reviewed PostgreSQL16 credential target required")
    connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('ocean-v1-beta-controller-credential-v1',0))"))
    existing = connection.execute(text("SELECT rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=:role"), {"role": ROLE}).first()
    base.attest_password_logging(connection)
    if version is None:
        if existing is not None or not store.empty():
            raise ValueError("Controller initialization refuses existing role or credential; inspect before reconciliation")
        password = secrets.token_urlsafe(48)
        dsn = URL.create("postgresql+psycopg2", username=ROLE, password=password,
            host="127.0.0.1", port=5432, database=DATABASE).render_as_string(hide_password=False)
        version = store.add(dsn)
    else:
        dsn = store.access(version)
        password = credential_url(dsn).password
        if existing is not None and (existing[0] is not True or any(existing[1:])):
            raise ValueError("Restricted existing controller role required for reconciliation")
    if existing is not None and connection.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE r.rolname=:role)"), {"role": ROLE}):
        raise ValueError("Unexpected controller role memberships")
    verifier = base.prepare_scram(connection, password, ROLE)
    base.attest_password_logging(connection)
    if existing is None:
        base.statement(connection, "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %s", ROLE, parameters=(verifier,))
        base.statement(connection, "ALTER ROLE {} IN DATABASE {} SET search_path TO public, pg_catalog", ROLE, DATABASE)
        base.statement(connection, "REVOKE {} FROM {}", ROLE, "postgres")
    else:
        base.statement(connection, "ALTER ROLE {} PASSWORD %s", ROLE, parameters=(verifier,))
    base.statement(connection, "GRANT CONNECT ON DATABASE {} TO {}", DATABASE, ROLE)
    base.statement(connection, "GRANT USAGE ON SCHEMA public TO {}", ROLE)
    # The caller uses this value only for an in-memory fresh login check.
    return version, dsn


def main():
    import argparse
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise ValueError("Exact controller credential arguments required")
    parser = Parser(description=__doc__)
    parser.add_argument("--confirm-project", required=True)
    parser.add_argument("--confirm-source", required=True)
    parser.add_argument("--reconcile-version")
    base = engine = check = None
    code, report = 2, {"state": "controller_credential_rejected_or_uncertain"}
    try:
        from context_operator import load_base_operator
        base = load_base_operator()
        args = parser.parse_args()
        manifest = json.loads((ROOT / "controller-credential-manifest.json").read_text())
        revision = os.environ["OCEAN_V1_CONTROLLER_CREDENTIAL_REVISION"]
        if (manifest["version"] != "ocean-v1-beta-controller-credential-v1"
                or args.confirm_project != PROJECT or args.confirm_source != revision or manifest["revision"] != revision
                or manifest["project_id"] != PROJECT or re.fullmatch(r"[a-f0-9]{40}", revision) is None
                or os.environ.get("OCEAN_V1_PROJECT_ID") != PROJECT or os.environ.get("DEPLOYMENT_ENV") != "production"
                or os.environ.get("OCEAN_V1_SQL_CONNECTION_NAME") != PROJECT + ":asia-northeast1:ocean-v1-beta-sql"
                or "DATABASE_URL" in os.environ or "config" in sys.modules
                or any(v.strip().lower() != "false" for k,v in os.environ.items() if k.startswith("ENABLE_V1_"))
                or hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != manifest["controller_credential_sha256"]):
            raise ValueError("Exact source/target required")
        url = make_url(os.environ["OCEAN_V1_BOOTSTRAP_DATABASE_URL"])
        if (url.drivername != "postgresql+psycopg2" or url.database != DATABASE or url.username != "postgres"
                or not url.password or url.host != "127.0.0.1" or url.port != 5432
                or dict(url.query) not in ({}, {"sslmode": "disable"})):
            raise ValueError("Exact bootstrap SQL target required")
        engine = create_engine(url, hide_parameters=True, connect_args={"connect_timeout": 10,
            "options": "-c statement_timeout=60000 -c lock_timeout=10000"})
        with engine.begin() as connection:
            version, dsn = initialize(connection, store=ControllerSecret(), base=base, version=args.reconcile_version)
        check = create_engine(credential_url(dsn), hide_parameters=True, connect_args={"connect_timeout": 10})
        with check.connect() as connection:
            if tuple(connection.execute(text("SELECT current_database(),current_user")).one()) != (DATABASE, ROLE):
                raise ValueError("Fresh controller login failed")
        report = {"state": "controller_credential_verified", "revision": revision,
            "secret_version": version, "plaintext_in_sql_or_output": False, "application_data_read": False}
        code = 0
    except Exception:
        pass
    finally:
        for item in (check, engine):
            if item is not None:
                item.dispose()
        if base is not None:
            try:
                report["proxy"] = base.stop_proxy()
            except Exception:
                code, report["state"] = 2, "proxy_shutdown_uncertain"
    print(json.dumps(report))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
