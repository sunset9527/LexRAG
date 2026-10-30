"""Stage 3 runtime bootstrap: safe per-statute orchestration and CLI contract."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import subprocess
import sys

from src.ingestion.statute_catalog import CatalogStatute
from src.ingestion.statute_ingestion import StatuteDefinition


ROOT = Path(__file__).resolve().parents[1]


def test_knowledge_base_service_registers_its_foreign_key_target_model():
    """A clean bootstrap process must resolve ``knowledge_bases.organization_id``."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.services.knowledge_base_service import KnowledgeBaseService; "
            "from app.db.base import Base; "
            "print([table.name for table in Base.metadata.sorted_tables])",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "organizations" in result.stdout


def _catalog_entry(tmp_path: Path, *, slug: str = "company-law") -> CatalogStatute:
    content = """中华人民共和国公司法
第一条 公司正文一。
第二条 公司正文二。
"""
    filename = f"{slug}.txt"
    (tmp_path / filename).write_text(content, encoding="utf-8")
    return CatalogStatute(
        definition=StatuteDefinition(slug, "中华人民共和国公司法", "company", "company-code"),
        clean_text_path=Path(filename),
        clean_text_sha256=sha256(content.encode("utf-8")).hexdigest(),
        article_count=2,
        first_article_number=1,
        last_article_number=2,
    )


class _KnowledgeBaseWriter:
    def __init__(self) -> None:
        self.created: list[dict[str, object]] = []
        self.rebuilt: list[tuple[str, str, object]] = []
        self.recovery_attempts: list[str] = []

    def create_knowledge_base(self, **kwargs):
        self.created.append(kwargs)

    def rebuild_bootstrap_statute(self, slug, *, content, identity):
        self.rebuilt.append((slug, content, identity))
        return {"status": "READY", "bootstrap_action": "rebuilt", "collection_name": identity.collection_name}

    def recover_expired_bootstrap_claim(self, slug, **_kwargs):
        self.recovery_attempts.append(slug)
        return False


def test_unavailable_snapshot_is_reported_without_creating_a_ready_knowledge_base(tmp_path: Path):
    from app.services.deployment_bootstrap_service import DeploymentBootstrapService

    entry = _catalog_entry(tmp_path)
    (tmp_path / entry.clean_text_path).unlink()
    writer = _KnowledgeBaseWriter()

    summary = DeploymentBootstrapService(writer, catalog=(entry,), project_root=tmp_path).bootstrap_all()

    assert summary["laws"] == [
        {"slug": "company-law", "status": "UNAVAILABLE", "error_code": "STATUTE_SOURCE_MISSING"}
    ]
    assert writer.created == []
    assert writer.rebuilt == []


def test_available_snapshot_builds_with_full_source_and_embedding_identity(tmp_path: Path):
    from app.services.deployment_bootstrap_service import DeploymentBootstrapService

    entry = _catalog_entry(tmp_path)
    writer = _KnowledgeBaseWriter()

    summary = DeploymentBootstrapService(writer, catalog=(entry,), project_root=tmp_path).bootstrap_all()

    assert summary["laws"][0]["status"] == "READY"
    assert writer.created == [
        {
            "name": "中华人民共和国公司法",
            "slug": "company-law",
            "law_area": "company",
            "is_system_shared": True,
        }
    ]
    slug, _content, identity = writer.rebuilt[0]
    assert slug == "company-law"
    assert identity.source_hash == entry.clean_text_sha256
    assert len(identity.embedding_fingerprint) == 64
    assert identity.index_schema_version == 1
    assert writer.recovery_attempts == ["company-law"]


def test_one_law_failure_isolated_and_does_not_make_the_other_law_unavailable(tmp_path: Path):
    from app.services.deployment_bootstrap_service import DeploymentBootstrapService

    good = _catalog_entry(tmp_path, slug="company-law")
    bad = _catalog_entry(tmp_path, slug="missing-law")
    (tmp_path / bad.clean_text_path).unlink()
    writer = _KnowledgeBaseWriter()

    summary = DeploymentBootstrapService(writer, catalog=(good, bad), project_root=tmp_path).bootstrap_all()

    assert [item["status"] for item in summary["laws"]] == ["READY", "UNAVAILABLE"]
    assert [item[0] for item in writer.rebuilt] == ["company-law"]


def test_runtime_bootstrap_cli_exposes_validate_statute_all_and_json_contracts():
    from scripts.bootstrap_runtime import parse_args

    assert parse_args(["validate", "--json"]).action == "validate"
    assert parse_args(["all"]).action == "all"
    args = parse_args(["statute", "company-law"])
    assert (args.action, args.slug) == ("statute", "company-law")
