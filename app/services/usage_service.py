"""组织日统计，借助 UsageEvent 保证重试幂等。"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.usage_daily import UsageDaily, UsageEvent


class UsageService:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def record_query(
        self,
        *,
        event_id: str,
        organization_id: int,
        actor_user_id: int | None,
        latency_ms: int,
        estimated_tokens: int,
    ) -> bool:
        with self.session_factory() as db:
            if db.get(UsageEvent, event_id) is not None:
                return False
            stat_date = date.today()
            daily = db.scalar(
                select(UsageDaily).where(
                    UsageDaily.organization_id == organization_id,
                    UsageDaily.stat_date == stat_date,
                )
            )
            if daily is None:
                daily = UsageDaily(organization_id=organization_id, stat_date=stat_date)
                db.add(daily)
                db.flush()
            daily.query_count += 1
            daily.success_count += 1
            daily.total_latency_ms += max(0, latency_ms)
            daily.estimated_token_count += max(0, estimated_tokens)
            db.add(
                UsageEvent(
                    event_id=event_id,
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                )
            )
            db.commit()
            return True
