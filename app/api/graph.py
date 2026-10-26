"""Law-graph visualization and traversal endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.admin import get_authorization_context
from app.api.dependencies import get_runtime
from app.runtime import RuntimeContainer
from app.schemas.graph import GraphQueryRequest
from app.services.authorization_service import AuthorizationContext

logger = logging.getLogger(__name__)
router = APIRouter(tags=["知识图谱"])


def _graph(runtime: RuntimeContainer) -> Any:
    graph = runtime.get("law_graph")
    if graph is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="图谱未初始化")
    return graph


def _require_read_access(context: AuthorizationContext) -> None:
    if not context.can("knowledge_bases:read"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")


@router.get("/graph")
def get_graph(
    law_name: str | None = Query(default=None),
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
    runtime: RuntimeContainer = Depends(get_runtime),
) -> dict[str, Any]:
    _require_read_access(authorization_context)
    graph = _graph(runtime)
    try:
        raw = graph.visualize_data()
        available_laws = sorted({str(node["law_name"]) for node in raw.get("nodes", []) if node.get("law_name")})
        selected_nodes = [
            node for node in raw.get("nodes", []) if law_name is None or node.get("law_name") == law_name
        ]
        selected_ids = {node.get("id") for node in selected_nodes}
        nodes = [
            {
                "id": node.get("id", ""),
                "name": f"第{node.get('article_number')}条" if node.get("article_number") else node.get("label", ""),
                "symbolSize": max(18, 20 + node.get("citation_count", 0) * 4),
                "category": 0,
                "law_name": node.get("law_name", ""),
            }
            for node in selected_nodes
        ]
        links = [
            {"source": edge["from"], "target": edge["to"]}
            for edge in raw.get("edges", [])
            if edge.get("from") in selected_ids and edge.get("to") in selected_ids
        ]
        return {
            "statistics": graph.get_statistics(),
            "most_cited": graph.get_most_cited(top_n=10),
            "available_laws": available_laws,
            "visualization_data": {"nodes": nodes, "links": links},
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("获取图谱失败 error_type=%s", type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="图谱读取失败") from exc


@router.post("/graph/query")
def query_graph(
    request: GraphQueryRequest,
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
    runtime: RuntimeContainer = Depends(get_runtime),
) -> dict[str, Any]:
    _require_read_access(authorization_context)
    graph = _graph(runtime)
    try:
        if request.article_id:
            return graph.get_citation_chain(request.article_id)
        return {"path": graph.find_shortest_path(request.source, request.target)}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("图谱查询失败 error_type=%s", type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="图谱查询失败") from exc
