"""LexRAG 本机只读 MCP server。默认 stdio，也可用受限的 Streamable HTTP。"""

import os
from uuid import uuid4

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from app.db import session as db_session
from app.db.session import init_db
from app.services.audit_service import AuditService
from app.services.authorization_service import AuthorizationService
from app.services.external_legal_source import MediaWikiLegalConceptSource
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.law_update_service import LawUpdateService

server = MCPServer(name="lexrag", title="LexRAG 法律检索", version="3.0")


def _services():
    if db_session.SessionLocal is None:
        raise RuntimeError("数据库未初始化")
    user_id = int(os.environ.get("MCP_DEMO_USER_ID", "0"))
    organization_id = int(os.environ.get("MCP_DEMO_ORGANIZATION_ID", "0"))
    context = AuthorizationService(db_session.SessionLocal).build_context(
        user_id=user_id, organization_id=organization_id
    )
    if not context.can("queries:create"):
        raise PermissionError("MCP 服务账号没有查询权限")
    return (
        context,
        KnowledgeBaseService(db_session.SessionLocal),
        LawUpdateService(db_session.SessionLocal),
        AuditService(db_session.SessionLocal),
    )


def _audit_mcp(context, audit, tool: str) -> None:
    try:
        audit.append_event(
            event_id=str(uuid4()),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            action="mcp.tool_called",
            target_type="mcp_tool",
            target_id=tool,
            status="success",
        )
    except Exception:
        pass


@server.tool()
async def search_local_statutes(query: str, knowledge_base_slug: str) -> list[dict]:
    """只读检索当前 MCP 服务账号所属组织的本地法规，返回来源片段。"""
    context, kb, _updates, audit = _services()
    kb.get_ready_collection_name_for_organization(
        knowledge_base_slug, organization_id=context.organization_id
    )
    matches = [
        item
        for item in kb.list_law_articles(knowledge_base_slug)
        if query in item["content"] or query in item["id"]
    ]
    _audit_mcp(context, audit, "search_local_statutes")
    return [
        {"source": item["id"], "content": item["content"][:800], "source_type": "local_statute"}
        for item in matches[:5]
    ]


@server.tool()
async def get_law_article(article_id: str, knowledge_base_slug: str) -> dict:
    """读取当前组织可见法规库的一条法条原文。"""
    context, kb, _updates, audit = _services()
    kb.get_visible_knowledge_base(knowledge_base_slug, organization_id=context.organization_id)
    for item in kb.list_law_articles(knowledge_base_slug):
        if item["id"] == article_id or str(item.get("article_number", "")) == article_id:
            _audit_mcp(context, audit, "get_law_article")
            return {
                "source": item["id"],
                "content": item["content"],
                "source_type": "local_statute",
            }
    raise ValueError("法条不存在或无访问权限")


@server.tool()
async def search_cases(query: str) -> list[dict]:
    """检索项目内已标注来源的案例；无案例检索器时明确返回空结果。"""
    context, _kb, _updates, audit = _services()
    if not context.can("cases:read"):
        raise PermissionError("MCP 服务账号没有案例检索权限")
    try:
        import api

        retriever = api.components.get("annual_case_retriever")
        rows = retriever.search(query, top_k=5) if retriever else []
    except Exception:
        rows = []
    _audit_mcp(context, audit, "search_cases")
    return [
        {
            "source_type": "local_case",
            "case_id": str(getattr(row, "case_id", "")),
            "content": str(getattr(row, "content", ""))[:800],
        }
        for row in rows
    ]


@server.tool()
async def search_wikipedia_legal_concept(query: str) -> list[dict]:
    """通过 MediaWiki 官方 REST API 查询概念；结果不是法律权威来源。"""
    context, _kb, _updates, audit = _services()
    result = await MediaWikiLegalConceptSource().search(query)
    _audit_mcp(context, audit, "search_wikipedia_legal_concept")
    return (
        result.items
        if result.available
        else [{"authority": "non_authoritative", "degraded": True, "reason": result.reason}]
    )


@server.tool()
async def get_law_update_status() -> dict:
    """返回当前组织的法规更新状态；外部来源未配置时不会伪造结果。"""
    context, _kb, updates, audit = _services()
    with updates.session_factory() as db:
        from app.models.law_update import LawSubscription

        items = db.query(LawSubscription).filter_by(organization_id=context.organization_id).all()
        _audit_mcp(context, audit, "get_law_update_status")
        return {
            "items": [
                {
                    "law_name": item.law_name,
                    "source_url": item.source_url,
                    "last_content_hash": item.last_content_hash,
                }
                for item in items
            ],
            "message": "仅显示已配置且可追溯的来源；未配置来源不会自动抓取。",
        }


if __name__ == "__main__":
    # MCP 是独立进程，不能依赖 FastAPI lifespan 初始化数据库。
    init_db()
    transport = os.environ.get("LEXRAG_MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        host = os.environ.get("MCP_HTTP_HOST", "127.0.0.1")
        port = int(os.environ.get("MCP_HTTP_PORT", "8001"))
        allowed_hosts = os.environ.get("MCP_ALLOWED_HOSTS", "localhost:8001,127.0.0.1:8001").split(
            ","
        )
        allowed_origins = os.environ.get(
            "MCP_ALLOWED_ORIGINS", "http://localhost,http://127.0.0.1"
        ).split(",")
        bearer_token = os.environ.get("MCP_HTTP_BEARER_TOKEN")
        if not bearer_token:
            raise RuntimeError("Streamable HTTP MCP 必须设置 MCP_HTTP_BEARER_TOKEN")
        import uvicorn
        from starlette.responses import JSONResponse

        http_app = server.streamable_http_app(
            transport_security=TransportSecuritySettings(
                allowed_hosts=[item.strip() for item in allowed_hosts if item.strip()],
                allowed_origins=[item.strip() for item in allowed_origins if item.strip()],
            ),
            host=host,
        )

        @http_app.middleware("http")
        async def require_bearer(request, call_next):
            if request.headers.get("authorization") != f"Bearer {bearer_token}":
                return JSONResponse({"detail": "MCP bearer token 无效"}, status_code=401)
            return await call_next(request)

        uvicorn.run(http_app, host=host, port=port, log_level="info")
    elif transport == "stdio":
        server.run("stdio")
    else:
        raise ValueError("LEXRAG_MCP_TRANSPORT 仅支持 stdio 或 streamable-http")
