"""Shared FastAPI dependencies for application-owned runtime services."""

from __future__ import annotations

from fastapi import Request

from app.runtime import RuntimeComponentUnavailable, RuntimeContainer


def get_runtime(request: Request) -> RuntimeContainer:
    """Return the lifespan-owned container without using module globals."""

    runtime = getattr(request.app.state, "runtime", None)
    if not isinstance(runtime, RuntimeContainer):
        raise RuntimeComponentUnavailable("runtime")
    return runtime
