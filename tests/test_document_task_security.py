"""Worker resource and error-redaction contracts."""

from pathlib import Path


def test_document_task_has_soft_and_hard_time_limits():
    from app.tasks.document_tasks import process_document_task
    from config import settings

    assert process_document_task.soft_time_limit == settings.document_task_soft_time_limit_seconds
    assert process_document_task.time_limit == settings.document_task_time_limit_seconds
    assert process_document_task.time_limit > process_document_task.soft_time_limit


def test_document_task_never_persists_raw_exception_text():
    source = Path("app/tasks/document_tasks.py").read_text(encoding="utf-8")

    assert "mark_failed(job_id, str(exc))" not in source
    assert "DOCUMENT_PROCESSING_FAILED" in source
