"""Authentication transport and registration-mode security contracts."""

from fastapi import Response

from app.api import auth as auth_api
from config import Settings


def test_bearer_token_takes_precedence_and_cookie_is_supported():
    assert auth_api.resolve_access_token("Bearer header-token", "cookie-token") == "header-token"
    assert auth_api.resolve_access_token(None, "cookie-token") == "cookie-token"
    assert auth_api.resolve_access_token("Basic ignored", None) is None


def test_browser_auth_cookie_is_httponly_and_same_site(monkeypatch):
    response = Response()
    monkeypatch.setattr(auth_api.settings, "auth_cookie_secure", True)
    monkeypatch.setattr(auth_api.settings, "auth_cookie_samesite", "lax")
    monkeypatch.setattr(auth_api.settings, "auth_cookie_name", "lexrag_session")

    auth_api.set_auth_cookie(response, "private-token")

    cookie = response.headers["set-cookie"]
    assert "lexrag_session=private-token" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Secure" in cookie


def test_registration_is_development_only():
    development = Settings(_env_file=None, app_mode="development", open_registration=True)
    production = Settings(_env_file=None, app_mode="production", open_registration=False)

    assert auth_api.registration_is_allowed(development)
    assert not auth_api.registration_is_allowed(production)
