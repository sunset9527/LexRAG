"""Dependency-aware readiness checks for the API process.

Each probe intentionally exposes only a stable component state.  Diagnostic
exceptions stay in logs at the caller boundary so passwords, paths and driver
messages cannot become a health endpoint response.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from threading import Event, Thread


ReadinessCheck = Callable[[], None]


@dataclass(frozen=True)
class ReadinessProbe:
    """One read-only dependency check with an endpoint-bounded timeout."""

    check: ReadinessCheck
    timeout_seconds: float = 3.0


@dataclass(frozen=True)
class ReadinessReport:
    """A safe, machine-readable snapshot of required dependencies."""

    ready: bool
    components: dict[str, str]


class ReadinessService:
    """Run required probes without leaking their exception details."""

    def __init__(self, checks: Mapping[str, ReadinessCheck | ReadinessProbe]) -> None:
        self._checks = {
            name: check if isinstance(check, ReadinessProbe) else ReadinessProbe(check)
            for name, check in checks.items()
        }

    def check(self) -> ReadinessReport:
        components: dict[str, str] = {}
        for name, probe in self._checks.items():
            components[name] = "ready" if self._run_probe(probe) else "not_ready"
        return ReadinessReport(
            ready=all(status == "ready" for status in components.values()),
            components=components,
        )

    @staticmethod
    def _run_probe(probe: ReadinessProbe) -> bool:
        """Bound a probe without exposing its error or blocking future checks.

        Probes are deliberately read-only.  A daemon thread allows a hung network
        driver to time out without keeping the health endpoint (or shutdown) stuck.
        """
        if probe.timeout_seconds <= 0:
            return False
        finished = Event()
        failed = [False]

        def run() -> None:
            try:
                probe.check()
            except Exception:
                failed[0] = True
            finally:
                finished.set()

        Thread(target=run, daemon=True, name="lexrag-readiness-probe").start()
        if not finished.wait(timeout=probe.timeout_seconds):
            return False
        return not failed[0]
