from __future__ import annotations

import pytest

import config


def _environment(**overrides: str) -> dict[str, str]:
    values = {
        "DEPLOYMENT_ENV": "production",
        "AUTH_MODE": "required",
        "AUTH_ALLOWED_PROVIDERS": "oidc",
        "PERSIST_LOCAL_CHAT": "false",
        "ENABLE_MOCK_LOGIN": "false",
        "INTERNAL_AUTH_SECRET": "api-signing-secret-that-is-long-and-random-123",
        "INTERNAL_AUTH_ISSUER": "onagawa-source-chat-frontend",
        "INTERNAL_AUTH_AUDIENCE": "onagawa-source-chat-api",
        "CORS_ORIGINS": "https://rag.example.org",
    }
    values.update(overrides)
    return values


def test_secure_production_configuration_is_accepted():
    config.validate_security_configuration(_environment())


@pytest.mark.parametrize(
    "providers",
    ["", "OIDC", "google_provider", "google,google", "mock-credentials"],
)
def test_auth_provider_allowlist_rejects_unsafe_values(providers):
    with pytest.raises(
        config.SecurityConfigurationError,
        match="AUTH_ALLOWED_PROVIDERS",
    ):
        config.validate_security_configuration(
            _environment(AUTH_ALLOWED_PROVIDERS=providers)
        )


def test_auth_provider_allowlist_accepts_stable_cloud_provider_ids():
    config.validate_security_configuration(
        _environment(AUTH_ALLOWED_PROVIDERS="google,tohoku")
    )


@pytest.mark.parametrize("deployment_env", ["staging", "production"])
def test_production_like_environments_reject_disabled_auth(deployment_env):
    with pytest.raises(
        config.SecurityConfigurationError,
        match="AUTH_MODE=disabled",
    ):
        config.validate_security_configuration(
            _environment(
                DEPLOYMENT_ENV=deployment_env,
                AUTH_MODE="disabled",
            )
        )


def test_production_rejects_local_chat_persistence():
    with pytest.raises(
        config.SecurityConfigurationError,
        match="PERSIST_LOCAL_CHAT",
    ):
        config.validate_security_configuration(
            _environment(PERSIST_LOCAL_CHAT="true")
        )


@pytest.mark.parametrize("deployment_env", ["staging", "production"])
def test_production_rejects_mock_login(deployment_env):
    with pytest.raises(
        config.SecurityConfigurationError,
        match="ENABLE_MOCK_LOGIN",
    ):
        config.validate_security_configuration(
            _environment(
                DEPLOYMENT_ENV=deployment_env,
                ENABLE_MOCK_LOGIN="true",
            )
        )


def test_local_mock_login_requires_normal_authentication():
    config.validate_security_configuration(
        _environment(
            DEPLOYMENT_ENV="test",
            AUTH_MODE="required",
            ENABLE_MOCK_LOGIN="true",
            CORS_ORIGINS="http://localhost:3000",
        )
    )
    assert config.mock_login_enabled(
        _environment(
            DEPLOYMENT_ENV="development",
            AUTH_MODE="required",
            ENABLE_MOCK_LOGIN="true",
            CORS_ORIGINS="http://localhost:3000",
        )
    )

    with pytest.raises(
        config.SecurityConfigurationError,
        match="requires AUTH_MODE=required",
    ):
        config.validate_security_configuration(
            _environment(
                DEPLOYMENT_ENV="development",
                AUTH_MODE="disabled",
                ENABLE_MOCK_LOGIN="true",
                INTERNAL_AUTH_SECRET="",
                CORS_ORIGINS="http://localhost:3000",
            )
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"INTERNAL_AUTH_SECRET": "short"}, "INTERNAL_AUTH_SECRET"),
        (
            {
                "INTERNAL_AUTH_SECRET": (
                    "replace-with-a-long-random-internal-secret"
                )
            },
            "INTERNAL_AUTH_SECRET",
        ),
        (
            {
                "INTERNAL_AUTH_SECRET": (
                    "<generate-a-different-random-value-of-at-least-32-characters>"
                )
            },
            "INTERNAL_AUTH_SECRET",
        ),
        ({"CORS_ORIGINS": "*"}, "HTTPS origins"),
        ({"CORS_ORIGINS": "http://rag.example.org"}, "HTTPS origins"),
        ({"CORS_ORIGINS": "https://"}, "HTTPS origins"),
        ({"CORS_ORIGINS": "https://rag.example.org/path"}, "HTTPS origins"),
        ({"CORS_ORIGINS": ""}, "CORS_ORIGINS"),
    ],
)
def test_production_rejects_unsafe_secrets_and_origins(overrides, message):
    with pytest.raises(config.SecurityConfigurationError, match=message):
        config.validate_security_configuration(_environment(**overrides))


def test_local_preview_can_disable_auth_and_opt_into_persistence():
    config.validate_security_configuration(
        _environment(
            DEPLOYMENT_ENV="development",
            AUTH_MODE="disabled",
            PERSIST_LOCAL_CHAT="true",
            INTERNAL_AUTH_SECRET="",
            CORS_ORIGINS="http://localhost:3000",
        )
    )


def test_local_authenticated_server_requires_a_signing_secret_at_startup():
    with pytest.raises(
        config.SecurityConfigurationError,
        match="INTERNAL_AUTH_SECRET",
    ):
        config.validate_security_configuration(
            _environment(
                DEPLOYMENT_ENV="development",
                INTERNAL_AUTH_SECRET="",
                CORS_ORIGINS="http://localhost:3000",
            ),
            require_auth_secret=True,
        )


@pytest.mark.parametrize(
    "value",
    ["sometimes", "enabled", "truthy"],
)
def test_invalid_local_persistence_boolean_is_rejected(value):
    with pytest.raises(
        config.SecurityConfigurationError,
        match="PERSIST_LOCAL_CHAT",
    ):
        config.validate_security_configuration(
            _environment(
                DEPLOYMENT_ENV="development",
                AUTH_MODE="disabled",
                PERSIST_LOCAL_CHAT=value,
                INTERNAL_AUTH_SECRET="",
                CORS_ORIGINS="http://localhost:3000",
            )
        )


@pytest.mark.parametrize("value", ["sometimes", "enabled", "truthy"])
def test_invalid_mock_login_boolean_is_rejected(value):
    with pytest.raises(
        config.SecurityConfigurationError,
        match="ENABLE_MOCK_LOGIN",
    ):
        config.validate_security_configuration(
            _environment(
                DEPLOYMENT_ENV="development",
                ENABLE_MOCK_LOGIN=value,
                CORS_ORIGINS="http://localhost:3000",
            )
        )


def test_runtime_configuration_accepts_supported_job_modes(monkeypatch):
    for mode in ("local", "external"):
        monkeypatch.setattr(config, "JOB_EXECUTION_MODE", mode)
        monkeypatch.setattr(config, "MODEL_PROVIDER", "ollama")
        config.validate_runtime_configuration()


def test_runtime_configuration_rejects_unknown_job_mode(monkeypatch):
    monkeypatch.setattr(config, "JOB_EXECUTION_MODE", "background-thread")

    with pytest.raises(
        config.RuntimeConfigurationError,
        match="JOB_EXECUTION_MODE",
    ):
        config.validate_runtime_configuration()


def test_vertex_runtime_requires_project(monkeypatch):
    monkeypatch.setattr(config, "MODEL_PROVIDER", "vertex")
    monkeypatch.setattr(config, "GOOGLE_CLOUD_PROJECT", "")

    with pytest.raises(
        config.RuntimeConfigurationError,
        match="GOOGLE_CLOUD_PROJECT",
    ):
        config.validate_runtime_configuration()


def test_vertex_runtime_accepts_bounded_configuration(monkeypatch):
    monkeypatch.setattr(config, "MODEL_PROVIDER", "vertex")
    monkeypatch.setattr(config, "GOOGLE_CLOUD_PROJECT", "example-project")
    monkeypatch.setattr(config, "GOOGLE_CLOUD_LOCATION", "global")
    monkeypatch.setattr(config, "MODEL_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(config, "MODEL_RETRY_INITIAL_SECONDS", 0.5)
    monkeypatch.setattr(config, "CHAT_MAX_OUTPUT_TOKENS", 1600)
    monkeypatch.setattr(config, "MODEL_REQUEST_TIMEOUT_SECONDS", 120)
    monkeypatch.setattr(config, "VERTEX_THINKING_BUDGET", 0)

    config.validate_runtime_configuration()
