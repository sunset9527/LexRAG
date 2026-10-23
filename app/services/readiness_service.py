"""Dependency-aware readiness checks for the API process.

Each probe intentionally exposes only a stable component state.  Diagnostic
exceptions stay in logs at the caller boundary so passwords, paths and driver
messages cannot become a health endpoint response.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass


ReadinessCheck = Callable[[], None]


@dataclass(frozen=True)
class ReadinessReport:
    """A safe, machine-readable snapshot of required dependencies."""

    ready: bool
    components: dict[str, str]


class ReadinessService:
    """Run required probes without leaking their exception details."""

    def __init__(self, checks: Mapping[str, ReadinessCheck]) -> None:
        self._checks = dict(checks)

    def check(self) -> ReadinessReport:
        components: dict[str, str] = {}
        for name, check in self._checks.items():
            try:
                check()
            except Exception:
                components[name] = "not_ready"
            else:
                components[name] = "ready"
        return ReadinessReport(
            ready=all(status == "ready" for status in components.values()),
            components=components,
        )
