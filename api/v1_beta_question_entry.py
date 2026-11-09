"""Explicit Research entry; the existing default read-only entry is preserved.

Only reviewed Research deployments override the container command to this
module. No migrations, grants, outbox sweep or provider call occurs at startup.
"""
import os
import sys


def validate_environment(environ, role):
    from sqlalchemy.engine import make_url
    from api.v1_beta_question_services import load_question_configuration, question_execution_fence
    if (role not in {"api", "controller"} or environ.get("DEPLOYMENT_ENV") != "production"
            or environ.get("OCEAN_V1_PROJECT_ID") != "ocean-v1-beta-20261101"
            or environ.get("OCEAN_V1_CATALOGUE_MODE") != "sealed-gcs-research-v1"
            or "DATABASE_URL" in environ):
        raise ValueError("Explicit beta research entry required")
    expected_user = "ocean_v1_serving" if role == "api" else "ocean_v1_research_controller"
    url = make_url(environ["OCEAN_V1_DATABASE_URL"])
    if (url.drivername != "postgresql+psycopg2" or url.database != "ocean_v1_beta"
            or url.username != expected_user or environ.get("OCEAN_V1_DATABASE_USER") != expected_user
            or not url.password or not set(url.query) <= {"host", "sslmode"}):
        raise ValueError("Exact beta research database identity required")
    import re
    connection = environ["OCEAN_V1_SQL_CONNECTION_NAME"]
    if re.fullmatch(r"ocean-v1-beta-20261101:asia-northeast1:ocean-v1-beta-[a-z0-9-]+", connection) is None:
        raise ValueError("Exact beta SQL instance required")
    socket = url.query.get("host")
    if socket is not None:
        if url.host not in {None, ""} or url.port is not None or socket != "/cloudsql/" + connection:
            raise ValueError("Exact beta SQL socket required")
    elif url.host not in {"127.0.0.1", "localhost"} or url.port != 5432:
        raise ValueError("Private beta SQL proxy required")
    question_execution_fence(environ)
    load_question_configuration(environ.get("OCEAN_V1_RESEARCH_CONFIG"),
        document_json=environ.get("OCEAN_V1_RESEARCH_CONFIG_JSON"))


def main():
    try:
        if len(sys.argv) != 2:
            raise ValueError("One explicit role required")
        role = sys.argv[1]
        validate_environment(os.environ, role)
        # The pinned base helper validates source/host identity only. Its default
        # read-only entry and execution fence are never changed by this module.
        from beta_entry import validate_serving_source
        validate_serving_source(os.environ)
        factory = "api.v1_host:create_from_environment" if role == "api" else "api.v1_research_controller_host:create_from_environment"
        os.execv(sys.executable, [sys.executable, "-m", "uvicorn", factory, "--factory",
            "--host", "127.0.0.1" if role == "api" else "0.0.0.0", "--port", "8000" if role == "api" else "8080",
            "--workers", "1", "--no-proxy-headers", "--no-access-log"])
    except Exception:
        print("Explicit beta research startup rejected", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
