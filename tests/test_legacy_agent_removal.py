from __future__ import annotations

from pathlib import Path


def test_legacy_react_workflow_is_not_shipped_from_the_agent_package() -> None:
    root = Path(__file__).parent.parent
    exports = (root / "src" / "agent" / "__init__.py").read_text(encoding="utf-8")

    assert not (root / "src" / "agent" / "workflow.py").exists()
    assert "LegalRAGWorkflow" not in exports
