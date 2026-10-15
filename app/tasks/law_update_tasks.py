"""本机法规快照监测任务。

任务只读取管理员已配置的本地快照目录，不对第三方法律网站发起未授权爬取。
每个订阅使用 ``{subscription_id}.txt`` 作为可核验的输入快照；检测到变化只创建待审核事件。
"""

from pathlib import Path

from sqlalchemy import select

from app.db import session as db_session
from app.db.session import init_db
from app.models.law_update import LawSourceSnapshot, LawSubscription, LawUpdateEvent
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.law_update_service import LawUpdateService
from app.services.metrics import LAW_UPDATE_TOTAL
from app.tasks.celery_app import celery_app


@celery_app.task(name="lexrag.check_law_update_snapshots")
def check_law_update_snapshots() -> dict[str, int | str]:
    snapshot_directory = Path(
        __import__("os").environ.get("LAW_UPDATE_SNAPSHOT_DIR", "/app/data/law_snapshots")
    )
    if not snapshot_directory.is_dir():
        return {"checked": 0, "changed": 0, "reason": "snapshot_directory_not_configured"}
    if db_session.SessionLocal is None:
        init_db()
    service = LawUpdateService(db_session.SessionLocal)
    with db_session.SessionLocal() as db:
        subscriptions = db.scalars(
            select(LawSubscription).where(LawSubscription.is_active.is_(True))
        ).all()
    changed = 0
    checked = 0
    for subscription in subscriptions:
        snapshot_path = snapshot_directory / f"{subscription.id}.txt"
        if not snapshot_path.is_file():
            continue
        checked += 1
        event = service.observe(
            subscription_id=subscription.id,
            organization_id=subscription.organization_id,
            content=snapshot_path.read_text(encoding="utf-8"),
        )
        if event is not None:
            changed += 1
            LAW_UPDATE_TOTAL.labels(status="pending_review").inc()
    return {"checked": checked, "changed": changed}


@celery_app.task(name="lexrag.rebuild_confirmed_law_version")
def rebuild_confirmed_law_version_task(event_id: int, organization_id: int) -> dict:
    """仅对已确认版本构建新 collection；切换前原 READY 库始终保持可用。"""
    if db_session.SessionLocal is None:
        init_db()
    with db_session.SessionLocal() as db:
        event = db.get(LawUpdateEvent, event_id)
        if event is None or event.status != "CONFIRMED":
            raise ValueError("法规更新尚未确认")
        subscription = db.get(LawSubscription, event.subscription_id)
        if (
            subscription is None
            or subscription.organization_id != organization_id
            or not subscription.knowledge_base_slug
        ):
            raise ValueError("法规订阅未关联当前组织法规库")
        snapshot = db.scalar(
            select(LawSourceSnapshot).where(
                LawSourceSnapshot.subscription_id == subscription.id,
                LawSourceSnapshot.content_hash == event.current_hash,
            )
        )
        if snapshot is None:
            raise ValueError("确认版本缺少来源快照")
        slug, content, digest = (
            subscription.knowledge_base_slug,
            snapshot.content,
            event.current_hash,
        )
    return KnowledgeBaseService(db_session.SessionLocal).rebuild_confirmed_law_version(
        slug, organization_id=organization_id, content=content, version_hash=digest
    )
