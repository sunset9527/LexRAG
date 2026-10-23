"""Stage 3 contracts for the queue runtime and public reverse proxy."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _compose() -> dict:
    return yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))


def _worker_health_module():
    path = ROOT / "scripts" / "check_worker_health.py"
    spec = importlib.util.spec_from_file_location("check_worker_health", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_worker_health_requires_broker_connection_and_targeted_ping():
    module = _worker_health_module()

    class Connection:
        def __init__(self):
            self.connected = False

        def ensure_connection(self, **kwargs):
            self.connected = True
            assert kwargs["max_retries"] == 1

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Inspector:
        def __init__(self):
            self.destination = None

        def ping(self):
            return {"lexrag-worker@worker": {"ok": "pong"}}

    class Control:
        def __init__(self, inspector):
            self.inspector = inspector

        def inspect(self, *, destination, timeout):
            self.inspector.destination = destination
            assert timeout == 5.0
            return self.inspector

    class App:
        def __init__(self):
            self.connection = Connection()
            self.inspector = Inspector()
            self.control = Control(self.inspector)

        def connection_for_read(self):
            return self.connection

    app = App()
    assert module.check_worker_health(app, "lexrag-worker@worker", timeout=5.0) is True
    assert app.connection.connected is True
    assert app.inspector.destination == ["lexrag-worker@worker"]


def test_worker_health_failure_is_redacted_and_does_not_echo_broker_url(capsys):
    module = _worker_health_module()

    class App:
        def connection_for_read(self):
            raise OSError("redis://user:secret@broker:6379/0 unavailable")

    assert module.main(["--hostname", "lexrag-worker@worker"], app_factory=lambda: App()) == 1
    captured = capsys.readouterr()
    assert "WORKER_BROKER_UNAVAILABLE" in captured.err
    assert "secret" not in captured.err
    assert "redis://" not in captured.err


def test_compose_worker_beat_and_health_contracts_are_stable():
    services = _compose()["services"]
    worker = services["worker"]
    beat = services["beat"]

    assert worker["hostname"] == "worker"
    assert "--hostname=lexrag-worker@%h" in worker["command"]
    assert worker["healthcheck"]["test"] == [
        "CMD",
        "python",
        "scripts/check_worker_health.py",
        "--hostname",
        "lexrag-worker@worker",
        "--timeout",
        "5",
    ]
    assert "--pool=solo" not in worker["command"]
    assert beat["hostname"] == "beat"
    assert "--pidfile=/tmp/lexrag-beat.pid" in beat["command"]
    assert "--schedule=/tmp/lexrag-beat-schedule" in beat["command"]


def test_celery_uses_default_task_time_limits_and_api_image_copies_health_script():
    celery_source = (ROOT / "app" / "tasks" / "celery_app.py").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "task_soft_time_limit=settings.document_task_soft_time_limit_seconds" in celery_source
    assert "task_time_limit=settings.document_task_time_limit_seconds" in celery_source
    assert "COPY scripts/check_worker_health.py ./scripts/check_worker_health.py" in dockerfile


def test_api_image_uses_the_non_dependency_live_probe_for_its_own_healthcheck():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "CMD curl -f http://localhost:8000/health/live || exit 1" in dockerfile


def test_nginx_preserves_api_rewrite_and_proxy_operational_contracts():
    nginx = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")

    assert "location /api/ {" in nginx
    # The trailing slash deliberately maps browser /api/query to backend /query.
    assert "proxy_pass http://api:8000/;" in nginx
    assert "client_max_body_size 50m;" in nginx
    assert "proxy_connect_timeout 10s;" in nginx
    assert "proxy_read_timeout 120s;" in nginx
    assert "proxy_send_timeout 120s;" in nginx
    assert "proxy_buffering off;" in nginx
    assert 'proxy_set_header X-Accel-Buffering "no";' in nginx
    assert "add_header X-Content-Type-Options \"nosniff\" always;" in nginx
    assert "add_header Referrer-Policy \"no-referrer\" always;" in nginx
    assert "gzip on;" in nginx
    assert "location /assets/ {" in nginx
    assert "Cache-Control \"public, immutable\"" in nginx
