import difflib
import hashlib
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from app.models.law_update import LawSubscription, LawUpdateEvent, LawSourceSnapshot, LawVersion

class LawUpdateService:
    def __init__(self, session_factory: sessionmaker): self.session_factory = session_factory
    def subscribe(self, *, organization_id: int, law_name: str, source_url: str, knowledge_base_slug: str | None = None) -> dict:
        with self.session_factory() as db:
            item = db.scalar(select(LawSubscription).where(LawSubscription.organization_id == organization_id, LawSubscription.law_name == law_name))
            if item is None:
                item = LawSubscription(organization_id=organization_id, law_name=law_name, source_url=source_url, knowledge_base_slug=knowledge_base_slug); db.add(item); db.commit(); db.refresh(item)
            elif knowledge_base_slug is not None:
                item.knowledge_base_slug = knowledge_base_slug; db.commit(); db.refresh(item)
            return self._subscription_payload(item)

    def list_subscriptions(self, *, organization_id: int) -> list[dict]:
        with self.session_factory() as db:
            return [self._subscription_payload(item) for item in db.scalars(
                select(LawSubscription)
                .where(LawSubscription.organization_id == organization_id)
                .order_by(LawSubscription.id)
            ).all()]

    def observe(self, *, subscription_id: int, organization_id: int, content: str) -> dict | None:
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        with self.session_factory() as db:
            sub = db.get(LawSubscription, subscription_id)
            if sub is None or sub.organization_id != organization_id or not sub.is_active: raise ValueError("法规订阅不存在或已停用")
            snapshot = db.scalar(select(LawSourceSnapshot).where(LawSourceSnapshot.subscription_id == sub.id, LawSourceSnapshot.content_hash == digest))
            if snapshot is None:
                snapshot = LawSourceSnapshot(subscription_id=sub.id, content_hash=digest, content=content)
                db.add(snapshot); db.flush()
            if sub.last_content_hash == digest: return None
            if db.scalar(select(LawUpdateEvent.id).where(LawUpdateEvent.subscription_id == sub.id, LawUpdateEvent.current_hash == digest, LawUpdateEvent.status == "PENDING_REVIEW")) is not None: return None
            if sub.last_content_hash is None:
                sub.last_content_hash = digest; db.commit(); return None
            previous = db.scalar(select(LawSourceSnapshot).where(LawSourceSnapshot.subscription_id == sub.id, LawSourceSnapshot.content_hash == sub.last_content_hash))
            previous_content = previous.content if previous else ""
            diff_lines = list(difflib.unified_diff(previous_content.splitlines(), content.splitlines(), fromfile="confirmed", tofile="candidate", lineterm=""))
            preview = "\n".join(diff_lines[:200]) or "检测到来源内容变化，待管理员确认。"
            event = LawUpdateEvent(subscription_id=sub.id, previous_hash=sub.last_content_hash, current_hash=digest, diff_preview=preview)
            db.add(event); db.commit(); db.refresh(event)
            return {"id": event.id, "status": event.status, "current_hash": event.current_hash}
    def confirm(self, *, event_id: int, organization_id: int, reviewer_user_id: int) -> dict:
        with self.session_factory() as db:
            event = db.get(LawUpdateEvent, event_id)
            if event is None or event.status != "PENDING_REVIEW": raise ValueError("更新事件不可确认")
            subscription = db.get(LawSubscription, event.subscription_id)
            if subscription is None or subscription.organization_id != organization_id: raise ValueError("更新事件不存在")
            subscription.last_content_hash = event.current_hash
            event.status = "CONFIRMED"; event.reviewer_user_id = reviewer_user_id; event.reviewed_at = datetime.now()
            snapshot = db.scalar(select(LawSourceSnapshot).where(LawSourceSnapshot.subscription_id == subscription.id, LawSourceSnapshot.content_hash == event.current_hash))
            if snapshot is None: raise ValueError("候选来源快照不存在")
            if db.scalar(select(LawVersion.id).where(LawVersion.subscription_id == subscription.id, LawVersion.content_hash == event.current_hash)) is None:
                db.add(LawVersion(subscription_id=subscription.id, snapshot_id=snapshot.id, content_hash=event.current_hash, confirmed_by_user_id=reviewer_user_id))
            db.commit()
            return {"id": event.id, "status": event.status, "knowledge_base_slug": subscription.knowledge_base_slug}

    @staticmethod
    def _subscription_payload(item: LawSubscription) -> dict:
        return {
            "id": item.id,
            "law_name": item.law_name,
            "source_url": item.source_url,
            "knowledge_base_slug": item.knowledge_base_slug,
            "is_active": item.is_active,
            "last_content_hash": item.last_content_hash,
        }
