"""Document-library upload and document-result endpoints."""

from __future__ import annotations

import hashlib
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)

from app.api.admin import get_authorization_context
from app.api.dependencies import get_runtime
from app.api.knowledge_bases import require_knowledge_base_access
from app.runtime import RuntimeContainer
from app.schemas.knowledge_bases import KnowledgeBaseCreateRequest
from app.security.uploads import UploadValidationError, build_isolated_upload_path, save_upload_file
from app.services.authorization_service import AuthorizationContext
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["文档库"])


def _component(runtime: RuntimeContainer, name: str, message: str) -> Any:
    component = runtime.get(name)
    if component is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=message)
    return component


def _append_audit_event(
    http_request: Request,
    context: AuthorizationContext,
    runtime: RuntimeContainer,
    *,
    action: str,
    target_type: str,
    target_id: str | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    service = runtime.get("audit_service")
    if service is None:
        return
    request_id = getattr(http_request.state, "request_id", None)
    seed = f"{request_id or uuid.uuid4().hex}:{action}:{target_type}:{target_id or ''}"
    try:
        service.append_event(
            event_id=hashlib.sha256(seed.encode("utf-8")).hexdigest(),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            status="success",
            request_id=request_id,
            metadata=metadata,
        )
    except Exception as exc:
        logger.error("审计写入失败 request_id=%s action=%s error_type=%s", request_id, action, type(exc).__name__)


def require_document_access(
    document_id: str,
    context: AuthorizationContext,
    runtime: RuntimeContainer,
    *,
    manage: bool = False,
) -> None:
    """Resolve document ownership before granting document-level access."""

    service = _component(runtime, "document_result_service", "文档结果服务未初始化")
    try:
        slug = service.get_knowledge_base_slug(document_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在或无访问权限") from exc
    require_knowledge_base_access(slug, context, runtime, manage=manage)


@router.post("/document-libraries", status_code=status.HTTP_201_CREATED)
def create_document_library(
    request: KnowledgeBaseCreateRequest,
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
    runtime: RuntimeContainer = Depends(get_runtime),
) -> dict[str, Any]:
    service = _component(runtime, "knowledge_base_service", "知识库服务未初始化")
    if not authorization_context.can("knowledge_bases:manage"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    return service.create_document_library(
        name=request.name,
        slug=request.slug,
        law_area=request.law_area,
        organization_id=authorization_context.organization_id,
    )


@router.post("/document-libraries/{slug}/documents", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    slug: str,
    http_request: Request,
    file: UploadFile = File(...),
    chunk_size: int = Form(800),
    chunk_overlap: int = Form(120),
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
    runtime: RuntimeContainer = Depends(get_runtime),
) -> dict[str, Any]:
    service = _component(runtime, "document_ingestion_service", "文档解析服务未初始化")
    require_knowledge_base_access(slug, authorization_context, runtime, manage=True)
    incoming_path = build_isolated_upload_path(
        settings.document_uploads_path,
        organization_id=authorization_context.organization_id,
        knowledge_base_slug=slug,
        original_filename=file.filename,
    )
    try:
        artifact = await save_upload_file(file, incoming_path, max_bytes=settings.upload_max_bytes)
        result = service.submit_document(
            knowledge_base_slug=slug,
            source_path=artifact.path,
            original_filename=artifact.original_filename,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        _append_audit_event(
            http_request,
            authorization_context,
            runtime,
            action="document.uploaded",
            target_type="knowledge_base",
            target_id=slug,
            metadata={"size_bytes": artifact.size_bytes},
        )
        return result
    except UploadValidationError as exc:
        code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE if "大小" in str(exc) else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    except ValueError as exc:
        code = status.HTTP_409_CONFLICT if "相同文件" in str(exc) else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    finally:
        await file.close()
        if incoming_path.exists():
            incoming_path.unlink()


@router.post("/document-libraries/{slug}/documents/batch", status_code=status.HTTP_202_ACCEPTED)
async def upload_documents(
    slug: str,
    http_request: Request,
    files: list[UploadFile] = File(...),
    chunk_size: int = Form(800),
    chunk_overlap: int = Form(120),
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
    runtime: RuntimeContainer = Depends(get_runtime),
) -> dict[str, list[dict[str, Any]]]:
    service = _component(runtime, "document_ingestion_service", "文档解析服务未初始化")
    require_knowledge_base_access(slug, authorization_context, runtime, manage=True)
    if len(files) > settings.upload_batch_max_files:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="批量上传文件数量超过限制")
    incoming_paths: list[Path] = []
    submissions: list[dict[str, Any]] = []
    aggregate_bytes = 0
    try:
        for file in files:
            incoming_path = build_isolated_upload_path(
                settings.document_uploads_path,
                organization_id=authorization_context.organization_id,
                knowledge_base_slug=slug,
                original_filename=file.filename,
            )
            artifact = await save_upload_file(file, incoming_path, max_bytes=settings.upload_max_bytes)
            incoming_paths.append(incoming_path)
            aggregate_bytes += artifact.size_bytes
            if aggregate_bytes > settings.upload_batch_max_bytes:
                raise UploadValidationError("批量上传总大小超过限制")
            submissions.append({"source_path": artifact.path, "original_filename": artifact.original_filename})
        result = {
            "items": service.submit_documents(
                knowledge_base_slug=slug,
                submissions=submissions,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        }
        _append_audit_event(
            http_request,
            authorization_context,
            runtime,
            action="document.batch_uploaded",
            target_type="knowledge_base",
            target_id=slug,
            metadata={"file_count": len(submissions), "size_bytes": aggregate_bytes},
        )
        return result
    except UploadValidationError as exc:
        code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE if "大小" in str(exc) or "数量" in str(exc) else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    finally:
        for file in files:
            await file.close()
        for incoming_path in incoming_paths:
            if incoming_path.exists():
                incoming_path.unlink()


@router.get("/document-libraries/{slug}/documents")
def list_documents(
    slug: str,
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
    runtime: RuntimeContainer = Depends(get_runtime),
) -> dict[str, list[dict[str, Any]]]:
    service = _component(runtime, "document_ingestion_service", "文档解析服务未初始化")
    require_knowledge_base_access(slug, authorization_context, runtime)
    try:
        return {"items": service.list_documents(slug)}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/documents/{document_id}")
def get_document(
    document_id: str,
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
    runtime: RuntimeContainer = Depends(get_runtime),
) -> dict[str, Any]:
    service = _component(runtime, "document_ingestion_service", "文档解析服务未初始化")
    require_document_access(document_id, authorization_context, runtime)
    try:
        return service.get_document(document_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/documents/{document_id}/result")
def get_document_result(
    document_id: str,
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
    runtime: RuntimeContainer = Depends(get_runtime),
) -> dict[str, Any]:
    service = _component(runtime, "document_result_service", "文档结果服务未初始化")
    require_document_access(document_id, authorization_context, runtime)
    try:
        return service.get_result(document_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/documents/{document_id}/pages")
def list_document_pages(
    document_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
    runtime: RuntimeContainer = Depends(get_runtime),
) -> dict[str, Any]:
    service = _component(runtime, "document_result_service", "文档结果服务未初始化")
    require_document_access(document_id, authorization_context, runtime)
    try:
        return service.list_pages(document_id, page=page, page_size=page_size)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/documents/{document_id}/relations")
def list_document_relations(
    document_id: str,
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
    runtime: RuntimeContainer = Depends(get_runtime),
) -> dict[str, Any]:
    service = _component(runtime, "document_result_service", "文档结果服务未初始化")
    require_document_access(document_id, authorization_context, runtime)
    try:
        return service.list_relations(document_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/documents/{document_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_document(
    document_id: str,
    http_request: Request,
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
    runtime: RuntimeContainer = Depends(get_runtime),
) -> dict[str, Any]:
    service = _component(runtime, "document_ingestion_service", "文档解析服务未初始化")
    require_document_access(document_id, authorization_context, runtime, manage=True)
    try:
        result = service.retry_document(document_id)
        _append_audit_event(
            http_request,
            authorization_context,
            runtime,
            action="document.retried",
            target_type="document",
            target_id=document_id,
        )
        return result
    except ValueError as exc:
        code = status.HTTP_409_CONFLICT if "仅失败" in str(exc) else status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=code, detail=str(exc)) from exc
