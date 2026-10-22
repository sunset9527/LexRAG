"""Runtime LLM configuration and SSRF policy contracts."""

import pytest

from config import Settings


def _policy(settings, addresses=("93.184.216.34",)):
    from app.security.runtime_llm import RuntimeLLMPolicy

    return RuntimeLLMPolicy(settings, resolver=lambda _host, _port: addresses)


def test_trusted_provider_is_accepted_without_custom_permission():
    settings = Settings(_env_file=None)

    result = _policy(settings).validate(
        base_url="https://api.deepseek.com/",
        model="deepseek-chat",
        allow_custom=False,
    )

    assert result.base_url == "https://api.deepseek.com"
    assert result.model == "deepseek-chat"
    assert result.timeout_seconds == settings.runtime_llm_timeout_seconds


@pytest.mark.parametrize(
    "base_url",
    [
        "http://127.0.0.1:8000/v1",
        "http://[::1]:8000/v1",
        "http://169.254.169.254/latest/meta-data",
        "https://user:password@example.com/v1",
        "https://example.com:22/v1",
    ],
)
def test_private_credentials_metadata_and_dangerous_ports_are_rejected(base_url):
    settings = Settings(_env_file=None)

    with pytest.raises(ValueError):
        _policy(settings).validate(base_url=base_url, model="safe-model", allow_custom=True)


def test_every_dns_result_must_be_public():
    settings = Settings(_env_file=None)

    with pytest.raises(ValueError, match="公网"):
        _policy(settings, addresses=("93.184.216.34", "10.0.0.7")).validate(
            base_url="https://models.example.com/v1",
            model="safe-model",
            allow_custom=True,
        )


def test_production_custom_endpoint_requires_permission_and_https():
    settings = Settings(
        _env_file=None,
        app_mode="production",
        open_registration=False,
        auth_cookie_secure=True,
        jwt_secret_key="stage2-test-only-secret-with-at-least-32-characters",
        mysql_password="stage2-test-only-database-password",
    )
    policy = _policy(settings)

    with pytest.raises(ValueError, match="权限"):
        policy.validate(
            base_url="https://models.example.com/v1",
            model="safe-model",
            allow_custom=False,
        )
    with pytest.raises(ValueError, match="HTTPS"):
        policy.validate(
            base_url="http://models.example.com/v1",
            model="safe-model",
            allow_custom=True,
        )


def test_model_name_and_redirect_policy_are_bounded():
    settings = Settings(_env_file=None)
    policy = _policy(settings)

    with pytest.raises(ValueError, match="模型"):
        policy.validate(
            base_url="https://api.deepseek.com",
            model="../unsafe model",
            allow_custom=False,
        )

    client, async_client = policy.build_http_clients()
    try:
        assert client.follow_redirects is False
        assert async_client.follow_redirects is False
    finally:
        client.close()


def test_http_client_connection_pool_uses_configured_concurrency(monkeypatch):
    captured = []

    class FakeClient:
        def __init__(self, **kwargs):
            captured.append(kwargs)

    monkeypatch.setattr("app.security.runtime_llm.httpx.Client", FakeClient)
    monkeypatch.setattr("app.security.runtime_llm.httpx.AsyncClient", FakeClient)
    settings = Settings(_env_file=None, runtime_llm_max_concurrency=3)

    _policy(settings).build_http_clients()

    assert len(captured) == 2
    for kwargs in captured:
        assert kwargs["follow_redirects"] is False
        assert kwargs["limits"].max_connections == 3
        assert kwargs["limits"].max_keepalive_connections == 3
