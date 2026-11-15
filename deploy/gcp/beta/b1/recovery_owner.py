"""Only one non-login B1 fixture account; no real account/history/credential copy.

The provider is deliberately outside the host's Google-only allowlist. This row
has no sign-in identity or credential. Its final state must be suspended.
"""
import json
import os

from sqlalchemy import create_engine, text

VERSION = "ocean-beta-b1-recovery-v1"
ACTOR_ID = "e59c73d1-b9f1-4d0f-a48c-1e2dc773b334"
PROFILE = ("b1_recovery_fixture", VERSION, "b1-recovery@fixture.invalid", "B1 recovery fixture", "admin", "internal")
BASE_REVISION = "84fe01714e426a66ee7b30559b69ebe05ef8f04f"


def check_target(connection):
    if (connection.dialect.name != "postgresql" or tuple(connection.execute(text(
            "SELECT current_database(),current_user")).one()) != ("ocean_v1_beta", "ocean_v1_migrator")
            or not 160000 <= int(connection.scalar(text("SHOW server_version_num"))) < 170000
            or any(connection.execute(text("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls "
                "FROM pg_roles WHERE rolname=current_user")).one())
            or connection.execute(text("SELECT version_num FROM public.alembic_version")).scalars().all() != ["20261027_0021"]):
        raise ValueError("Exact restricted beta fixture operator required")


def operate(connection, phase):
    if phase not in {"enroll", "suspend", "restore", "close"}:
        raise ValueError("Fixed fixture phase required")
    check_target(connection)
    params = dict(zip(("provider", "subject", "email", "display", "role", "kind"), PROFILE))
    params["id"] = ACTOR_ID
    row = connection.execute(text("SELECT auth_provider,auth_subject,email,display_name,role,account_type,status "
        "FROM public.app_user WHERE id=CAST(:id AS uuid) FOR UPDATE"), params).first()
    if phase == "enroll":
        if row is not None or connection.scalar(text("SELECT EXISTS(SELECT 1 FROM public.app_user "
                "WHERE email=:email OR (auth_provider=:provider AND auth_subject=:subject))"), params):
            raise ValueError("Fixture exists or conflicts; inspect rather than replay")
        connection.execute(text("INSERT INTO public.app_user "
            "(id,auth_provider,auth_subject,email,display_name,role,account_type,status) "
            "VALUES(CAST(:id AS uuid),:provider,:subject,:email,:display,:role,:kind,'active')"), params)
        expected = "active"
    else:
        if row is None or tuple(row[:6]) != PROFILE:
            raise ValueError("Exact isolated fixture profile required")
        previous, expected = ("suspended", "active") if phase == "restore" else ("active", "suspended")
        if row[6] != previous:
            raise ValueError("Fixture status already changed; inspect rather than replay")
        params.update(previous=previous, expected=expected)
        changed = connection.execute(text("UPDATE public.app_user SET status=:expected "
            "WHERE id=CAST(:id AS uuid) AND status=:previous RETURNING status"), params).scalars().all()
        if changed != [expected]:
            raise ValueError("One exact fixture status change required")
    return {"version": VERSION, "state": "fixture_account_verified", "phase": phase,
        "fixture_id": ACTOR_ID, "status": expected, "google_sign_in_available": False,
        "real_account_history_credentials_grants_or_scientific_bytes_changed": False}


def main(phase):
    import datetime
    engine = base = None
    result, code = {"version": VERSION, "state": "fixture_operation_rejected_or_uncertain", "phase": phase}, 2
    try:
        import research_operator
        from context_operator import load_base_operator
        base = load_base_operator()
        selected = research_operator.configuration(os.environ,
            confirm_project="ocean-v1-beta-20261101", confirm_source=BASE_REVISION)
        engine = create_engine(selected.dsn, hide_parameters=True, pool_pre_ping=True,
            connect_args={"connect_timeout": 10, "options": "-c statement_timeout=30000 -c lock_timeout=10000"})
        with engine.begin() as connection:
            result = operate(connection, phase)
        with engine.connect() as connection:
            row = connection.execute(text("SELECT auth_provider,auth_subject,email,display_name,role,account_type,status "
                "FROM public.app_user WHERE id=CAST(:id AS uuid)"), {"id": ACTOR_ID}).one()
            if tuple(row[:6]) != PROFILE or row[6] != result["status"]:
                raise ValueError("Fresh fixture readback differs")
        result["fresh_connection_readback_verified"] = True
        code = 0
    except Exception:
        # Never emit a DB/provider exception, DSN, credential or data row.
        result["state"] = "fixture_operation_rejected_or_uncertain"
    finally:
        if engine is not None:
            engine.dispose()
        if base is not None:
            try:
                result["proxy"] = base.stop_proxy()
            except Exception:
                code, result["state"] = 2, "proxy_shutdown_uncertain"
        result["captured_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        print(json.dumps(result, sort_keys=True))
    return code
