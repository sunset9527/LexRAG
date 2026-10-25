"""Probe a Celery worker through its broker without exposing broker credentials."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class WorkerBrokerUnavailable(RuntimeError):
    """The worker health probe could not establish a broker connection."""


class WorkerUnresponsive(RuntimeError):
    """The named Celery worker did not answer the control ping."""


def check_worker_health(app: Any, hostname: str, *, timeout: float) -> bool:
    """Return true only when the broker connects and the exact worker replies."""

    try:
        with app.connection_for_read() as connection:
            connection.ensure_connection(max_retries=1)
    except Exception as error:
        raise WorkerBrokerUnavailable from error

    try:
        replies = app.control.inspect(destination=[hostname], timeout=timeout).ping()
    except Exception as error:
        raise WorkerUnresponsive from error

    if not replies or replies.get(hostname, {}).get("ok") != "pong":
        raise WorkerUnresponsive
    return True


def _celery_app() -> Any:
    from app.tasks.celery_app import celery_app

    return celery_app


def main(
    argv: Sequence[str] | None = None,
    *,
    app_factory: Callable[[], Any] = _celery_app,
) -> int:
    parser = argparse.ArgumentParser(description="Check a named Celery worker through its broker.")
    parser.add_argument("--hostname", required=True)
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args(argv)

    try:
        check_worker_health(app_factory(), args.hostname, timeout=args.timeout)
    except WorkerBrokerUnavailable:
        print("WORKER_BROKER_UNAVAILABLE", file=sys.stderr)
        return 1
    except WorkerUnresponsive:
        print("WORKER_UNRESPONSIVE", file=sys.stderr)
        return 1

    print("WORKER_HEALTHY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
