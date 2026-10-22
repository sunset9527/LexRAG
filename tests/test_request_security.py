"""Pure request-boundary security contracts.

The repository's ASGI integration suite exercises middleware wiring. These unit
contracts deliberately avoid opening the Windows asyncio self-pipe so they can
also run in restricted development sandboxes.
"""

import importlib
import importlib.util
import re


def _module():
    spec = importlib.util.find_spec("app.security.request_security")
    assert spec is not None, "request security module has not been implemented"
    return importlib.import_module("app.security.request_security")


def test_valid_request_id_is_preserved_and_invalid_value_is_replaced():
    security = _module()

    assert security.normalize_request_id("stage2-Req_123") == "stage2-Req_123"
    generated = security.normalize_request_id("bad id\r\nInjected: true")

    assert generated != "bad id\r\nInjected: true"
    assert re.fullmatch(r"[A-Za-z0-9._-]{8,64}", generated)


def test_internal_error_payload_never_contains_exception_text():
    security = _module()
    marker = "PRIVATE_INTERNAL_MARKER"

    payload = security.internal_error_payload("request-123", RuntimeError(marker))

    assert payload == {
        "code": "INTERNAL_ERROR",
        "message": "服务暂时不可用，请稍后重试",
        "request_id": "request-123",
    }
    assert marker not in str(payload)


def test_log_redaction_masks_credentials_and_bearer_tokens():
    security = _module()
    marker = "stage2-secret-marker"
    message = (
        f"Authorization: Bearer {marker} api_key={marker} "
        f'"password": "{marker}"'
    )

    redacted = security.redact_log_message(message)

    assert marker not in redacted
    assert "[REDACTED]" in redacted
