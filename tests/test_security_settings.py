"""Stage 2 security configuration contracts."""

import pytest

import config


def test_security_defaults_are_explicit_and_bounded():
    settings = config.Settings(_env_file=None)

    assert settings.app_mode == "development"
    assert settings.open_registration is True
    assert settings.auth_cookie_secure is False
    assert 0 < settings.upload_max_bytes <= 50 * 1024 * 1024
    assert 0 < settings.runtime_llm_timeout_seconds <= 120
    assert 0 <= settings.runtime_llm_max_retries <= 3
    assert 0 < settings.runtime_llm_max_concurrency <= 32


def test_production_rejects_demonstration_secrets():
    settings = config.Settings(
        _env_file=None,
        app_mode="production",
        open_registration=False,
        auth_cookie_secure=True,
    )

    with pytest.raises(config.SecurityConfigurationError) as captured:
        config.validate_security_settings(settings)

    message = str(captured.value)
    assert "jwt_secret_key" in message
    assert "mysql_password" in message
    assert settings.jwt_secret_key not in message
    assert settings.mysql_password not in message


def test_production_accepts_explicit_secure_configuration():
    settings = config.Settings(
        _env_file=None,
        app_mode="production",
        open_registration=False,
        auth_cookie_secure=True,
        jwt_secret_key="stage2-test-only-secret-with-at-least-32-characters",
        mysql_password="stage2-test-only-database-password",
    )

    config.validate_security_settings(settings)


def test_production_validates_the_active_database_url_password():
    secure = config.Settings(
        _env_file=None,
        app_mode="production",
        open_registration=False,
        auth_cookie_secure=True,
        jwt_secret_key="stage2-test-only-secret-with-at-least-32-characters",
        database_url="mysql+pymysql://lexrag:safe-production-password@db:3306/lexrag",
    )
    config.validate_security_settings(secure)

    insecure = secure.model_copy(
        update={"database_url": "mysql+pymysql://root:123456@db:3306/lexrag"}
    )
    with pytest.raises(config.SecurityConfigurationError, match="database_url"):
        config.validate_security_settings(insecure)


@pytest.mark.parametrize(
    ("override", "expected_key"),
    [
        ({"runtime_llm_timeout_seconds": 0}, "runtime_llm_timeout_seconds"),
        ({"runtime_llm_max_retries": 9}, "runtime_llm_max_retries"),
        ({"runtime_llm_max_concurrency": 0}, "runtime_llm_max_concurrency"),
        ({"upload_max_bytes": 0}, "upload_max_bytes"),
    ],
)
def test_invalid_resource_limits_are_rejected_in_every_mode(override, expected_key):
    settings = config.Settings(_env_file=None, **override)

    with pytest.raises(config.SecurityConfigurationError, match=expected_key):
        config.validate_security_settings(settings)
