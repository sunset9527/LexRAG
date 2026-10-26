"""Static privacy guardrails for the active request and retrieval path."""

import re
from pathlib import Path

from config import Settings

ROOT = Path(__file__).parent.parent
ACTIVE_FILES = [
    ROOT / "api.py",
    ROOT / "app/api/auth.py",
    ROOT / "app/api/scenarios.py",
    ROOT / "app/services/langfuse_helper.py",
    ROOT / "src/retrieval/query_rewriter.py",
    ROOT / "src/retrieval/intent_router.py",
    ROOT / "src/retrieval/context_compressor.py",
    ROOT / "src/retrieval/law_retriever.py",
    ROOT / "src/retrieval/case_retriever.py",
    ROOT / "src/workflow/legal_evidence_workflow.py",
    ROOT / "app/api/queries.py",
    ROOT / "app/services/query_route_service.py",
    ROOT / "app/services/query_run_service.py",
    ROOT / "app/services/query_execution_service.py",
    ROOT / "app/tasks/document_tasks.py",
]


def test_sensitive_llm_tracing_is_disabled_by_default():
    assert Settings(_env_file=None).langfuse_enabled is False


def test_active_path_does_not_interpolate_exception_text_into_logs():
    unsafe = re.compile(r"logger\.(?:debug|info|warning|error|exception)\(f[^\n]*\{(?:e|exc)\}")
    findings = []
    for path in ACTIVE_FILES:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if unsafe.search(line):
                findings.append(f"{path.relative_to(ROOT)}:{line_number}")

    assert findings == []


def test_query_content_and_unhandled_exception_text_are_not_public():
    source = (ROOT / "api.py").read_text(encoding="utf-8")

    assert 'logger.info(f"处理查询: {request.query}")' not in source
    assert not re.search(r"status_code=500,\s*detail=str\(", source)


def test_persisted_job_errors_store_codes_not_exception_text():
    paths = [
        ROOT / "app/services/case_book_processor.py",
        ROOT / "app/services/document_ingestion_service.py",
        ROOT / "app/services/document_structure_service.py",
        ROOT / "app/services/knowledge_base_service.py",
        ROOT / "app/tasks/document_tasks.py",
    ]
    findings = []
    unsafe = re.compile(r"(?:error_message\s*=|[\"']error[\"']\s*:)[^\n]*str\((?:e|exc)\)")
    for path in paths:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if unsafe.search(line):
                findings.append(f"{path.relative_to(ROOT)}:{line_number}")
    assert findings == []


def test_active_query_workflow_logs_do_not_include_raw_queries():
    paths = [
        ROOT / "src/workflow/legal_evidence_workflow.py",
        ROOT / "app/api/queries.py",
        ROOT / "app/services/query_route_service.py",
        ROOT / "app/services/query_run_service.py",
        ROOT / "app/services/query_execution_service.py",
    ]
    unsafe_fragments = ("{question}", "{enhanced_query}", "{state.query}")

    findings = []
    for path in paths:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "logger." in line and any(fragment in line for fragment in unsafe_fragments):
                findings.append(f"{path.relative_to(ROOT)}:{line_number}")
    assert findings == []


def test_project_logs_do_not_interpolate_exception_messages_or_emit_tracebacks():
    unsafe_interpolation = re.compile(
        r"logger\.(?:debug|info|warning|error|exception)\(f[^\n]*\{(?:e|exc)\}"
    )
    findings = []
    for root_name in ("app", "src"):
        for path in (ROOT / root_name).rglob("*.py"):
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if unsafe_interpolation.search(line) or "logger.exception(" in line:
                    findings.append(f"{path.relative_to(ROOT)}:{line_number}")
    assert findings == []
