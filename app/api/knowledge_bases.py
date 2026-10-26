"""Statute knowledge-base management endpoints."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.admin import get_authorization_context
from app.api.dependencies import get_runtime
from app.runtime import RuntimeContainer
from app.schemas.knowledge_bases import (
    KnowledgeBaseCreateRequest,
    KnowledgeBaseListResponse,
    KnowledgeBaseRebuildRequest,
    UploadRequest,
)
from app.services.authorization_service import AuthorizationContext
from app.services.knowledge_base_service import KnowledgeBaseBusyError
from src.ingestion.index_identity import (
    IndexIdentityError,
    IndexIdentityMismatchError,
    LegacyCollectionIdentityError,
)

router = APIRouter(tags=["知识库"])


def require_knowledge_base_access(
    slug: str,
    context: AuthorizationContext,
    runtime: RuntimeContainer,
    *,
    manage: bool = False,
) -> None:
    """Enforce organization-scoped knowledge-base access for every caller."""

    required_permission = "knowledge_bases:manage" if manage else "knowledge_bases:read"
    if not context.can(required_permission):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    service = runtime.get("knowledge_base_service")
    if service is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="知识库服务未初始化")
    try:
        service.get_visible_knowledge_base(
            slug,
            organization_id=context.organization_id,
            require_owner=manage,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在或无访问权限"
        ) from exc


def _knowledge_base_service(runtime: RuntimeContainer) -> Any:
    service = runtime.get("knowledge_base_service")
    if service is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="知识库服务未初始化")
    return service


def _invalidate_rebuilt_collection_runtime(runtime: RuntimeContainer, result: dict[str, Any]) -> None:
    collection_name = result.get("collection_name")
    registry = runtime.get("query_runtime_registry")
    if isinstance(collection_name, str) and collection_name and registry is not None:
        registry.invalidate(collection_name)


def _append_rebuild_audit(
    http_request: Request,
    context: AuthorizationContext,
    runtime: RuntimeContainer,
    request: UploadRequest,
) -> None:
    service = runtime.get("audit_service")
    if service is None:
        return
    request_id = getattr(http_request.state, "request_id", None)
    seed = f"{request_id or uuid.uuid4().hex}:knowledge_base.rebuilt:{request.knowledge_base_slug}"
    try:
        service.append_event(
            event_id=hashlib.sha256(seed.encode("utf-8")).hexdigest(),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            action="knowledge_base.rebuilt",
            target_type="knowledge_base",
            target_id=request.knowledge_base_slug,
            status="success",
            request_id=request_id,
            metadata={"content_length": len(request.content)},
        )
    except Exception:
        return


@router.get("/knowledge-bases", response_model=KnowledgeBaseListResponse)
def list_knowledge_bases(
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
    runtime: RuntimeContainer = Depends(get_runtime),
) -> KnowledgeBaseListResponse:
    """List knowledge bases visible to the active organization."""

    service = _knowledge_base_service(runtime)
    if not authorization_context.can("knowledge_bases:read"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    return KnowledgeBaseListResponse(
        items=service.list_visible_knowledge_bases(organization_id=authorization_context.organization_id)
    )


@router.post("/knowledge-bases", status_code=status.HTTP_201_CREATED)
def create_knowledge_base(
    request: KnowledgeBaseCreateRequest,
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
    runtime: RuntimeContainer = Depends(get_runtime),
) -> dict[str, Any]:
    """Create an empty statute knowledge-base registration."""

    service = _knowledge_base_service(runtime)
    if not authorization_context.can("knowledge_bases:manage"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    return service.create_knowledge_base(
        name=request.name,
        slug=request.slug,
        law_area=request.law_area,
        organization_id=authorization_context.organization_id,
    )


@router.post("/knowledge-bases/{slug}/rebuild")
def rebuild_knowledge_base(
    slug: str,
    request: KnowledgeBaseRebuildRequest,
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
    runtime: RuntimeContainer = Depends(get_runtime),
) -> dict[str, Any]:
    """Rebuild a statute index and invalidate the matching runtime cache."""

    service = _knowledge_base_service(runtime)
    require_knowledge_base_access(slug, authorization_context, runtime, manage=True)
    try:
        result = service.rebuild_knowledge_base(slug, content=request.content)
        _invalidate_rebuilt_collection_runtime(runtime, result)
        return result
    except IndexIdentityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "INDEX_IDENTITY_REBUILD_REQUIRED",
                "message": "知识库索引与当前嵌入配置不兼容，需要以新索引身份重新构建",
            },
        ) from exc
    except KnowledgeBaseBusyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/knowledge-bases/{slug}/laws")
def list_knowledge_base_laws(
    slug: str,
    start_article: int | None = Query(default=None, ge=1),
    end_article: int | None = Query(default=None, ge=1),
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
    runtime: RuntimeContainer = Depends(get_runtime),
) -> dict[str, list[dict[str, Any]]]:
    """Read statute articles from a visible knowledge base."""

    service = _knowledge_base_service(runtime)
    require_knowledge_base_access(slug, authorization_context, runtime)
    try:
        return {
            "items": service.list_law_articles(
                slug,
                start_article=start_article,
                end_article=end_article,
            )
        }
    except IndexIdentityError as exc:
        error_code = (
            LegacyCollectionIdentityError.code
            if isinstance(exc, LegacyCollectionIdentityError)
            else IndexIdentityMismatchError.code
            if isinstance(exc, IndexIdentityMismatchError)
            else "INDEX_IDENTITY_REBUILD_REQUIRED"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": error_code, "message": "知识库索引与当前嵌入配置不兼容，请重建后重试"},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/knowledge-bases/{slug}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge_base(
    slug: str,
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
    runtime: RuntimeContainer = Depends(get_runtime),
) -> None:
    """Delete a visible, non-rebuilding knowledge base."""

    service = _knowledge_base_service(runtime)
    require_knowledge_base_access(slug, authorization_context, runtime, manage=True)
    try:
        service.delete_knowledge_base(slug)
    except KnowledgeBaseBusyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/upload")
def upload_law(
    http_request: Request,
    request: UploadRequest,
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
    runtime: RuntimeContainer = Depends(get_runtime),
) -> dict[str, Any]:
    """Compatibility endpoint for rebuilding a statute knowledge base."""

    require_knowledge_base_access(
        request.knowledge_base_slug,
        authorization_context,
        runtime,
        manage=True,
    )
    service = _knowledge_base_service(runtime)
    try:
        result = service.rebuild_knowledge_base(request.knowledge_base_slug, content=request.content)
        _invalidate_rebuilt_collection_runtime(runtime, result)
        _append_rebuild_audit(http_request, authorization_context, runtime, request)
        return result
    except KnowledgeBaseBusyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="知识库正在重建") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在或无访问权限") from exc
