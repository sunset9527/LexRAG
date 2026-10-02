"""Celery entrypoint for durable legal-scenario jobs."""

from app.db import session as db_session
from app.db.session import init_db
from app.services.scenario_runtime import create_runtime_scenario_service
from app.tasks.celery_app import celery_app


@celery_app.task(name="lexrag.process_scenario")
def process_scenario_task(user_id: int, scenario_id: str, organization_id: int | None = None) -> dict:
    """处理已持久化场景任务；不传递、不落库用户模型密钥。"""
    if db_session.SessionLocal is None:
        init_db()
    service = create_runtime_scenario_service()
    result = service.process(user_id=user_id, scenario_id=scenario_id, organization_id=organization_id)
    if result is None:
        raise ValueError("场景任务不存在或不属于当前用户")
    return result
