"""自定义文档上传及异步解析任务的服务层。"""

from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from shutil import copyfile
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document_job import DocumentJob
from app.models.knowledge_base import KnowledgeBase


class DocumentIngestionService:
    """处理上传前校验、持久化与任务投递，不在 API 请求内执行解析。"""

    allowed_extensions = {".pdf", ".docx"}
    max_file_size = 20 * 1024 * 1024
    min_chunk_size = 200
    max_chunk_size = 2000

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        uploads_root: Path,
        task_dispatcher: Callable[[str], None],
    ):
        self._session_factory = session_factory
        self._uploads_root = Path(uploads_root)
        self._task_dispatcher = task_dispatcher

    def submit_document(
        self,
        *,
        knowledge_base_slug: str,
        source_path: Path,
        original_filename: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> dict[str, Any]:
        """保存一份上传文件，并投递后续异步处理任务。"""
        source_path = Path(source_path)
        extension = Path(original_filename).suffix.lower()
        if extension not in self.allowed_extensions:
            raise ValueError("仅支持 PDF 或 DOCX 文件")
        if not source_path.is_file():
            raise ValueError("上传文件不存在")
        file_size = source_path.stat().st_size
        if file_size > self.max_file_size:
            raise ValueError("文件大小不能超过 20 MB")
        self._validate_chunk_options(chunk_size, chunk_overlap)
        content_hash = sha256(source_path.read_bytes()).hexdigest()

        with self._session_factory() as session:
            knowledge_base = session.scalar(
                select(KnowledgeBase).where(KnowledgeBase.slug == knowledge_base_slug)
            )
            if knowledge_base is None:
                raise ValueError(f"知识库不存在: {knowledge_base_slug}")
            if knowledge_base.type != "document":
                raise ValueError("只能向自定义文档知识库上传文件")
            duplicate = session.scalar(
                select(DocumentJob).where(
                    DocumentJob.knowledge_base_slug == knowledge_base_slug,
                    DocumentJob.sha256 == content_hash,
                    DocumentJob.status != "FAILED",
                )
            )
            if duplicate is not None:
                raise ValueError("相同文件已在该知识库中处理或入库")

            job_id = str(uuid4())
            destination = self._uploads_root / knowledge_base_slug / f"{job_id}{extension}"
            destination.parent.mkdir(parents=True, exist_ok=True)
            copyfile(source_path, destination)
            job = DocumentJob(
                id=job_id,
                knowledge_base_slug=knowledge_base_slug,
                original_filename=original_filename,
                storage_path=str(destination.resolve()),
                file_type=extension.removeprefix("."),
                file_size=file_size,
                sha256=content_hash,
                status="UPLOADED",
                progress=0,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            session.add(job)
            session.commit()
            session.refresh(job)
            result = self._serialize(job)

        self._task_dispatcher(job_id)
        return result

    def submit_documents(
        self,
        *,
        knowledge_base_slug: str,
        submissions: list[dict[str, Any]],
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[dict[str, Any]]:
        """逐个提交批量文件；任一文件失败仅返回自身错误。"""
        results: list[dict[str, Any]] = []
        for submission in submissions:
            source_path = Path(submission["source_path"])
            original_filename = str(submission["original_filename"])
            try:
                job = self.submit_document(
                    knowledge_base_slug=knowledge_base_slug,
                    source_path=source_path,
                    original_filename=original_filename,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )
            except ValueError as exc:
                results.append({"original_filename": original_filename, "error": str(exc)})
            else:
                results.append({"original_filename": original_filename, "job": job})
        return results

    def list_documents(self, knowledge_base_slug: str) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            self._get_document_library(session, knowledge_base_slug)
            jobs = session.scalars(
                select(DocumentJob)
                .where(DocumentJob.knowledge_base_slug == knowledge_base_slug)
                .order_by(DocumentJob.created_at.desc())
            ).all()
            return [self._serialize(job) for job in jobs]

    def get_document(self, job_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            job = session.get(DocumentJob, job_id)
            if job is None:
                raise ValueError(f"文档任务不存在: {job_id}")
            return self._serialize(job)

    def retry_document(self, job_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            job = session.get(DocumentJob, job_id)
            if job is None:
                raise ValueError(f"文档任务不存在: {job_id}")
            if job.status != "FAILED":
                raise ValueError("仅失败任务允许重试")
            job.status = "UPLOADED"
            job.progress = 0
            job.error_message = None
            job.started_at = None
            job.completed_at = None
            session.commit()
            session.refresh(job)
            result = self._serialize(job)
        self._task_dispatcher(job_id)
        return result

    def _validate_chunk_options(self, chunk_size: int, chunk_overlap: int) -> None:
        if not self.min_chunk_size <= chunk_size <= self.max_chunk_size:
            raise ValueError("分块大小必须在 200 到 2000 之间")
        if not 0 <= chunk_overlap < chunk_size:
            raise ValueError("分块重叠必须大于等于 0 且小于分块大小")

    @staticmethod
    def _get_document_library(session: Session, slug: str) -> KnowledgeBase:
        knowledge_base = session.scalar(
            select(KnowledgeBase).where(KnowledgeBase.slug == slug)
        )
        if knowledge_base is None:
            raise ValueError(f"知识库不存在: {slug}")
        if knowledge_base.type != "document":
            raise ValueError("只能操作自定义文档知识库")
        return knowledge_base

    @staticmethod
    def _serialize(job: DocumentJob) -> dict[str, Any]:
        return {
            "id": job.id,
            "knowledge_base_slug": job.knowledge_base_slug,
            "original_filename": job.original_filename,
            "file_type": job.file_type,
            "file_size": job.file_size,
            "sha256": job.sha256,
            "status": job.status,
            "progress": job.progress,
            "chunk_size": job.chunk_size,
            "chunk_overlap": job.chunk_overlap,
            "page_count": job.page_count,
            "character_count": job.character_count,
            "chunk_count": job.chunk_count,
            "error_message": job.error_message,
        }
