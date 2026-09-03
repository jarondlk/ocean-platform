"""
Centralized configuration for OCEAN Platform.

All paths, database URLs, model settings, and environment variable
overrides are collected here so that every module imports from one place.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Mapping, Optional
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Project root – resolves relative to this file
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Data directory layout
# ---------------------------------------------------------------------------
DATA_DIR       = Path(
    os.environ.get("DATA_DIR", str(PROJECT_ROOT / "data"))
).expanduser()
RAW_DIR        = DATA_DIR / "raw"
RAW_CTD_DIR    = RAW_DIR / "ctd"
RAW_META_DIR   = RAW_DIR / "meta"
RAW_SST_DIR    = RAW_DIR / "sst"       # symlink or copy from onagawa_sst_subset/
RAW_ANEMONE_DIR = RAW_DIR / "anemone"
NORMALIZED_DIR = DATA_DIR / "normalized"
ANEMONE_NORMALIZED_DIR = NORMALIZED_DIR / "anemone"
CANONICAL_DIR  = DATA_DIR / "canonical"
SERVING_DIR    = DATA_DIR / "serving"
ANALYSIS_DIR    = DATA_DIR / "analysis"
EDNA_ARTIFACT_URI = os.environ.get('EDNA_ARTIFACT_URI', '').strip()
EDNA_CACHE_DIR = Path(os.environ.get('EDNA_CACHE_DIR', '/tmp/ocean-edna-cache')).expanduser().resolve()
if EDNA_ARTIFACT_URI:
    RAW_ANEMONE_DIR = EDNA_CACHE_DIR / 'raw'
    ANEMONE_NORMALIZED_DIR = EDNA_CACHE_DIR / 'normalized'
EDNA_ANALYSIS_RECIPE = Path(os.environ.get('EDNA_ANALYSIS_RECIPE', str(ANALYSIS_DIR / 'edna_recipe.json'))).expanduser()
RELIABILITY_DIR = DATA_DIR / "reliability"
PROVENANCE_DIR  = DATA_DIR / "provenance"
EVALUATION_DIR  = DATA_DIR / "evaluation"
PROVENANCE_SNAPSHOT_URI = os.environ.get(
    "PROVENANCE_SNAPSHOT_URI",
    f"file://{PROVENANCE_DIR}",
).strip()
PROVENANCE_READ_MODE = os.environ.get(
    "PROVENANCE_READ_MODE",
    "build",
).strip().lower()
PROVENANCE_CACHE_TTL_SECONDS = int(
    os.environ.get("PROVENANCE_CACHE_TTL_SECONDS", "60")
)
DATABASE_BACKUP_DIR = Path(
    os.environ.get("DATABASE_BACKUP_DIR", str(DATA_DIR / "backups"))
).expanduser()
ANEMONE_CONTRACT_PATH = PROJECT_ROOT / "data_contracts" / "anemone_mifish.json"
ANEMONE_BASE_URL = os.environ.get(
    "ANEMONE_BASE_URL",
    "https://db.anemone.bio/dist/MiFish/ANEMONE/",
).strip()

# Satellite SST source (NetCDF subset files)
SST_NETCDF_DIR = Path(
    os.environ.get("SST_NETCDF_DIR", str(PROJECT_ROOT / "onagawa_sst_subset"))
).expanduser()

# Raw Himawari .DAT files (optional, parsed via satpy if available)
HIMAWARI_RAW_DIR = Path(
    os.environ.get("HIMAWARI_RAW_DIR", str(PROJECT_ROOT / "himawari_raw"))
).expanduser()

# ---------------------------------------------------------------------------
# Known raw file registry (matches notebook FILES dict)
# ---------------------------------------------------------------------------
RAW_FILES = {
    "ctd":                      RAW_CTD_DIR / "CTD_Onagawa.tsv",
    "runid":                    RAW_META_DIR / "runid.tsv",
    "read_summary":             RAW_META_DIR / "01.read_summary_gt1kb.tsv",
    "coverage_log":             RAW_META_DIR / "03.coverage.log.tsv",
    "kraken_genus_sample_tsv":  RAW_META_DIR / "Kraken.genus-sample.tsv",
    "kraken_genus_sample_txt":  RAW_META_DIR / "Kraken.genus-sample.txt",
    "kraken_upper_group_sample": RAW_META_DIR / "Kraken.upper_group-sample.txt",
    "kraken_genus_group":       RAW_META_DIR / "Kraken.genus-group.tsv",
    "metaeuk_genus_sample":     RAW_META_DIR / "MetaEuk.genus-sample.tsv",
    "genus_group":              RAW_META_DIR / "genus-group.tsv",
    "gn_consistency":           RAW_META_DIR / "gn.consistency.tsv",
    "km_consistency":           RAW_META_DIR / "km.consistency.tsv",
}

# ---------------------------------------------------------------------------
# Default Onagawa monitoring station coordinates
# ---------------------------------------------------------------------------
ONAGAWA_LAT = 38.42907415591698
ONAGAWA_LON = 141.4775733277202

# Regional bounding box for SST subset
SST_LAT_MIN, SST_LAT_MAX = 38.0, 39.0
SST_LON_MIN, SST_LON_MAX = 141.0, 142.0

# ---------------------------------------------------------------------------
# Reliability Ensurance thresholds
# ---------------------------------------------------------------------------
SST_CTD_AGREEMENT_THRESHOLD = float(os.environ.get("SST_CTD_THRESHOLD", "2.0"))
DIVERSITY_ANOMALY_SIGMA = float(os.environ.get("DIVERSITY_ANOMALY_SIGMA", "2.0"))

# ---------------------------------------------------------------------------
# Database (PostgreSQL + pgvector)
# ---------------------------------------------------------------------------
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://ocean:ocean@localhost:5433/ocean_platform",
)


def _environment_int(name: str, default: int, *, minimum: int = 0) -> int:
    raw_value = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _optional_environment_path(name: str) -> Optional[Path]:
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser() if value else None


ANEMONE_DOWNLOAD_USERNAME_FILE = _optional_environment_path(
    "ANEMONE_DOWNLOAD_USERNAME_FILE"
)
ANEMONE_DOWNLOAD_PASSWORD_FILE = _optional_environment_path(
    "ANEMONE_DOWNLOAD_PASSWORD_FILE"
)
ANEMONE_MAX_FILES = _environment_int("ANEMONE_MAX_FILES", 2000, minimum=1)
ANEMONE_MAX_BYTES = _environment_int(
    "ANEMONE_MAX_BYTES",
    512 * 1024 * 1024,
    minimum=1,
)
ANEMONE_NORMALIZATION_VERSION = _environment_int(
    "ANEMONE_NORMALIZATION_VERSION",
    1,
    minimum=1,
)


# Keep each autoscaled application instance's connection footprint bounded.
# The local defaults remain intentionally small and can be tuned independently
# for Cloud Run and Cloud SQL through environment variables.
DATABASE_POOL_SIZE = _environment_int("DATABASE_POOL_SIZE", 5, minimum=1)
DATABASE_MAX_OVERFLOW = _environment_int("DATABASE_MAX_OVERFLOW", 2)
DATABASE_POOL_TIMEOUT = _environment_int(
    "DATABASE_POOL_TIMEOUT",
    30,
    minimum=1,
)
DATABASE_POOL_RECYCLE = _environment_int(
    "DATABASE_POOL_RECYCLE",
    1800,
    minimum=1,
)


def database_engine_options() -> dict[str, object]:
    """Return bounded SQLAlchemy pool settings for application processes."""

    return {
        "pool_pre_ping": True,
        "pool_size": DATABASE_POOL_SIZE,
        "max_overflow": DATABASE_MAX_OVERFLOW,
        "pool_timeout": DATABASE_POOL_TIMEOUT,
        "pool_recycle": DATABASE_POOL_RECYCLE,
    }


DATABASE_BACKUP_CONTAINER = os.environ.get(
    "DATABASE_BACKUP_CONTAINER",
    "ocean_pgvector",
).strip()

# Web processes may run background jobs locally, while autoscaled cloud
# services must delegate durable work to an external job runner.
JOB_EXECUTION_MODE = os.environ.get(
    "JOB_EXECUTION_MODE",
    "local",
).strip().lower()
LOCAL_MAX_ACTIVE_JOBS = _environment_int("LOCAL_MAX_ACTIVE_JOBS", 1, minimum=1)

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
# ``required`` is the secure default. Tests and intentionally isolated local
# development may explicitly opt out with AUTH_MODE=disabled.
DEPLOYMENT_ENV = os.environ.get("DEPLOYMENT_ENV", "development").strip().lower()
AUTH_MODE = os.environ.get("AUTH_MODE", "required").strip().lower()
PERSIST_LOCAL_CHAT = os.environ.get("PERSIST_LOCAL_CHAT", "false").strip().lower()
ENABLE_MOCK_LOGIN = os.environ.get(
    "ENABLE_MOCK_LOGIN",
    "false",
).strip().lower()
INTERNAL_AUTH_SECRET = os.environ.get("INTERNAL_AUTH_SECRET", "")
INTERNAL_AUTH_ISSUER = os.environ.get(
    "INTERNAL_AUTH_ISSUER",
    "ocean-platform-frontend",
)
INTERNAL_AUTH_AUDIENCE = os.environ.get(
    "INTERNAL_AUTH_AUDIENCE",
    "ocean-platform-api",
)
AUTH_ALLOWED_PROVIDERS = tuple(
    provider.strip()
    for provider in os.environ.get("AUTH_ALLOWED_PROVIDERS", "oidc").split(",")
    if provider.strip()
)


class SecurityConfigurationError(RuntimeError):
    """Raised when authentication could start in an unsafe configuration."""


_ALLOWED_DEPLOYMENT_ENVS = frozenset(
    {"development", "test", "staging", "production"}
)
_PRODUCTION_LIKE_ENVS = frozenset({"staging", "production"})
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off", ""})
_PLACEHOLDER_MARKERS = (
    "replace-with",
    "not-configured",
    "change-me",
    "changeme",
    "placeholder",
    "generate-",
)
_AUTH_PROVIDER_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,31}$")


def _security_setting(
    environ: Mapping[str, str],
    name: str,
    default: str,
) -> str:
    return str(environ.get(name, default)).strip()


def _security_flag(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise SecurityConfigurationError(
        f"{name} must be one of true/false, yes/no, on/off, or 1/0"
    )


def _placeholder_secret(value: str) -> bool:
    lowered = value.lower()
    return (
        "<" in value
        or ">" in value
        or any(marker in lowered for marker in _PLACEHOLDER_MARKERS)
    )


def _valid_https_origin(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and not parsed.path
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    )


def validate_security_configuration(
    environ: Optional[Mapping[str, str]] = None,
    *,
    require_auth_secret: bool = False,
) -> None:
    """Validate authentication settings without logging any secret values.

    Production-like deployments are always strict. Local development may use
    disabled authentication, but an API process that is actually serving
    authenticated requests must still provide a non-placeholder signing secret.
    """

    env = os.environ if environ is None else environ
    deployment_env = _security_setting(
        env,
        "DEPLOYMENT_ENV",
        DEPLOYMENT_ENV,
    ).lower()
    if deployment_env not in _ALLOWED_DEPLOYMENT_ENVS:
        raise SecurityConfigurationError(
            "DEPLOYMENT_ENV must be development, test, staging, or production"
        )

    auth_mode = _security_setting(env, "AUTH_MODE", AUTH_MODE).lower()
    if auth_mode not in {"required", "disabled"}:
        raise SecurityConfigurationError(
            "AUTH_MODE must be either required or disabled"
        )
    allowed_providers = tuple(
        provider.strip()
        for provider in _security_setting(
            env,
            "AUTH_ALLOWED_PROVIDERS",
            ",".join(AUTH_ALLOWED_PROVIDERS),
        ).split(",")
        if provider.strip()
    )
    if auth_mode == "required" and not allowed_providers:
        raise SecurityConfigurationError(
            "AUTH_ALLOWED_PROVIDERS must contain at least one provider"
        )
    if (
        len(set(allowed_providers)) != len(allowed_providers)
        or any(
            not _AUTH_PROVIDER_ID_PATTERN.fullmatch(provider)
            or provider == "mock-credentials"
            for provider in allowed_providers
        )
    ):
        raise SecurityConfigurationError(
            "AUTH_ALLOWED_PROVIDERS must be unique lowercase provider IDs "
            "containing only letters, numbers, and hyphens"
        )

    persist_local_chat = _security_flag(
        _security_setting(
            env,
            "PERSIST_LOCAL_CHAT",
            PERSIST_LOCAL_CHAT,
        ),
        "PERSIST_LOCAL_CHAT",
    )
    mock_login = _security_flag(
        _security_setting(
            env,
            "ENABLE_MOCK_LOGIN",
            ENABLE_MOCK_LOGIN,
        ),
        "ENABLE_MOCK_LOGIN",
    )
    production_like = deployment_env in _PRODUCTION_LIKE_ENVS
    if production_like and auth_mode != "required":
        raise SecurityConfigurationError(
            "AUTH_MODE=disabled is forbidden in staging and production"
        )
    if production_like and persist_local_chat:
        raise SecurityConfigurationError(
            "PERSIST_LOCAL_CHAT is forbidden in staging and production"
        )
    if persist_local_chat and auth_mode != "disabled":
        raise SecurityConfigurationError(
            "PERSIST_LOCAL_CHAT may only be used with AUTH_MODE=disabled"
        )
    if production_like and mock_login:
        raise SecurityConfigurationError(
            "ENABLE_MOCK_LOGIN is forbidden in staging and production"
        )
    if mock_login and auth_mode != "required":
        raise SecurityConfigurationError(
            "ENABLE_MOCK_LOGIN requires AUTH_MODE=required"
        )

    if auth_mode == "required" and (require_auth_secret or production_like):
        secret = _security_setting(
            env,
            "INTERNAL_AUTH_SECRET",
            INTERNAL_AUTH_SECRET,
        )
        if len(secret) < 32 or _placeholder_secret(secret):
            raise SecurityConfigurationError(
                "INTERNAL_AUTH_SECRET must be a non-placeholder value "
                "of at least 32 characters"
            )
        issuer = _security_setting(
            env,
            "INTERNAL_AUTH_ISSUER",
            INTERNAL_AUTH_ISSUER,
        )
        audience = _security_setting(
            env,
            "INTERNAL_AUTH_AUDIENCE",
            INTERNAL_AUTH_AUDIENCE,
        )
        if not issuer or not audience:
            raise SecurityConfigurationError(
                "INTERNAL_AUTH_ISSUER and INTERNAL_AUTH_AUDIENCE are required"
            )

    if production_like:
        raw_origins = _security_setting(env, "CORS_ORIGINS", "")
        origins = [
            origin.strip()
            for origin in raw_origins.split(",")
            if origin.strip()
        ]
        if not origins:
            raise SecurityConfigurationError(
                "CORS_ORIGINS must list the production frontend origin"
            )
        if any(
            origin == "*" or not _valid_https_origin(origin)
            for origin in origins
        ):
            raise SecurityConfigurationError(
                "Production CORS_ORIGINS must contain explicit HTTPS origins"
            )


def production_like_environment(
    environ: Optional[Mapping[str, str]] = None,
) -> bool:
    env = os.environ if environ is None else environ
    deployment_env = _security_setting(
        env,
        "DEPLOYMENT_ENV",
        DEPLOYMENT_ENV,
    ).lower()
    return deployment_env in _PRODUCTION_LIKE_ENVS


def mock_login_enabled(
    environ: Optional[Mapping[str, str]] = None,
) -> bool:
    """Return whether the guarded development mock login is enabled."""

    env = os.environ if environ is None else environ
    validate_security_configuration(env)
    return _security_flag(
        _security_setting(
            env,
            "ENABLE_MOCK_LOGIN",
            ENABLE_MOCK_LOGIN,
        ),
        "ENABLE_MOCK_LOGIN",
    )

# ---------------------------------------------------------------------------
# LLM / Embedding
# ---------------------------------------------------------------------------
MODEL_PROVIDER = os.environ.get("MODEL_PROVIDER", "ollama").strip().lower()
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "nomic-embed-text")
CHAT_MODEL      = os.environ.get("CHAT_MODEL", "qwen2.5:14b-instruct")
GOOGLE_CLOUD_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
GOOGLE_CLOUD_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global").strip()
CHAT_MAX_OUTPUT_TOKENS = int(os.environ.get("CHAT_MAX_OUTPUT_TOKENS", "1600"))
MODEL_MAX_ATTEMPTS = int(os.environ.get("MODEL_MAX_ATTEMPTS", "3"))
MODEL_RETRY_INITIAL_SECONDS = float(
    os.environ.get("MODEL_RETRY_INITIAL_SECONDS", "0.5")
)
MODEL_REQUEST_TIMEOUT_SECONDS = int(
    os.environ.get("MODEL_REQUEST_TIMEOUT_SECONDS", "120")
)
VERTEX_THINKING_BUDGET = int(os.environ.get("VERTEX_THINKING_BUDGET", "0"))

# Embedding dimension (nomic-embed-text → 768)
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "768"))


def _model_allowlist(name: str, default: str) -> frozenset[str]:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return frozenset({default})
    return frozenset(item.strip() for item in raw_value.split(",") if item.strip())


ALLOWED_CHAT_MODELS = _model_allowlist("ALLOWED_CHAT_MODELS", CHAT_MODEL)
ALLOWED_EMBEDDING_MODELS = _model_allowlist(
    "ALLOWED_EMBEDDING_MODELS",
    EMBEDDING_MODEL,
)
CHAT_RETENTION_DAYS = _environment_int("CHAT_RETENTION_DAYS", 90, minimum=1)


class RuntimeConfigurationError(ValueError):
    """Raised when runtime settings are invalid or unsafe for the platform."""


def validate_runtime_configuration() -> None:
    if JOB_EXECUTION_MODE not in {"local", "external"}:
        raise RuntimeConfigurationError(
            "JOB_EXECUTION_MODE must be either local or external"
        )
    if production_like_environment() and JOB_EXECUTION_MODE == "local":
        raise RuntimeConfigurationError(
            "Production-like environments must use JOB_EXECUTION_MODE=external"
        )
    if PROVENANCE_READ_MODE not in {"build", "snapshot"}:
        raise RuntimeConfigurationError(
            "PROVENANCE_READ_MODE must be either build or snapshot"
        )
    if not 1 <= PROVENANCE_CACHE_TTL_SECONDS <= 3600:
        raise RuntimeConfigurationError(
            "PROVENANCE_CACHE_TTL_SECONDS must be between 1 and 3600"
        )
    if not MODEL_PROVIDER:
        raise RuntimeConfigurationError("MODEL_PROVIDER must not be empty")
    if not ALLOWED_CHAT_MODELS:
        raise RuntimeConfigurationError("ALLOWED_CHAT_MODELS must not be empty")
    if CHAT_MODEL not in ALLOWED_CHAT_MODELS:
        raise RuntimeConfigurationError("ALLOWED_CHAT_MODELS must include CHAT_MODEL")
    if not ALLOWED_EMBEDDING_MODELS:
        raise RuntimeConfigurationError(
            "ALLOWED_EMBEDDING_MODELS must not be empty"
        )
    if EMBEDDING_MODEL not in ALLOWED_EMBEDDING_MODELS:
        raise RuntimeConfigurationError(
            "ALLOWED_EMBEDDING_MODELS must include EMBEDDING_MODEL"
        )
    if CHAT_RETENTION_DAYS > 3650:
        raise RuntimeConfigurationError(
            "CHAT_RETENTION_DAYS must not exceed 3650"
        )
    if MODEL_PROVIDER == "vertex" and not GOOGLE_CLOUD_PROJECT:
        raise RuntimeConfigurationError(
            "MODEL_PROVIDER=vertex requires GOOGLE_CLOUD_PROJECT"
        )
    if not GOOGLE_CLOUD_LOCATION:
        raise RuntimeConfigurationError("GOOGLE_CLOUD_LOCATION must not be empty")
    if CHAT_MAX_OUTPUT_TOKENS < 1:
        raise RuntimeConfigurationError("CHAT_MAX_OUTPUT_TOKENS must be positive")
    if MODEL_MAX_ATTEMPTS not in {1, 2, 3}:
        raise RuntimeConfigurationError("MODEL_MAX_ATTEMPTS must be between 1 and 3")
    if MODEL_RETRY_INITIAL_SECONDS < 0:
        raise RuntimeConfigurationError(
            "MODEL_RETRY_INITIAL_SECONDS must not be negative"
        )
    if not 1 <= MODEL_REQUEST_TIMEOUT_SECONDS <= 300:
        raise RuntimeConfigurationError(
            "MODEL_REQUEST_TIMEOUT_SECONDS must be between 1 and 300"
        )
    if not 0 <= VERTEX_THINKING_BUDGET <= 4096:
        raise RuntimeConfigurationError(
            "VERTEX_THINKING_BUDGET must be between 0 and 4096"
        )


def ensure_dirs() -> None:
    """Create all output directories if they don't exist."""
    for d in [NORMALIZED_DIR, CANONICAL_DIR, SERVING_DIR, PROVENANCE_DIR,
              ANALYSIS_DIR, RELIABILITY_DIR, EVALUATION_DIR,
              DATABASE_BACKUP_DIR]:
        d.mkdir(parents=True, exist_ok=True)
