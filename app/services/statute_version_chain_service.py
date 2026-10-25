"""服务层：法规版本链只在可验证时允许走向索引。"""

from collections.abc import Callable, Mapping, Sequence
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.legal_source_import import LegalSourceImport
from app.models.statute_version_chain import StatuteVersionChain, StatuteVersionChainMember


class StatuteVersionChainError(ValueError):
    """版本链不满足可追溯或适用边界。"""


class StatuteVersionChainService:
    def __init__(self, session_factory: Callable[[], Session]):
        self._session_factory = session_factory

    def create_chain(
        self,
        *,
        law_slug: str,
        target_version_id: str,
        effective_from: date,
        members: Sequence[Mapping[str, Any]],
        effective_to: date | None = None,
        consolidated_source_import_id: int | None = None,
    ) -> dict[str, Any]:
        if not members:
            raise StatuteVersionChainError("版本链至少需要一个来源成员")
        if effective_to is not None and effective_to < effective_from:
            raise StatuteVersionChainError("版本链失效日期不能早于生效日期")

        with self._session_factory() as session:
            if session.scalar(
                select(StatuteVersionChain.id).where(
                    StatuteVersionChain.target_version_id == target_version_id
                )
            ) is not None:
                raise StatuteVersionChainError("目标版本已存在")

            source_ids = [int(member["source_import_id"]) for member in members]
            sources = {
                item.id: item
                for item in session.scalars(
                    select(LegalSourceImport).where(LegalSourceImport.id.in_(source_ids))
                ).all()
            }
            if set(sources) != set(source_ids):
                raise StatuteVersionChainError("版本链引用了不存在的候选来源")
            if any(item.law_slug != law_slug for item in sources.values()):
                raise StatuteVersionChainError("版本链成员必须属于同一法律")
            if any(item.authority_status != "VERIFIED" for item in sources.values()):
                raise StatuteVersionChainError("版本链成员尚未完成权威核验")
            if consolidated_source_import_id is not None:
                consolidated = sources.get(consolidated_source_import_id)
                if consolidated is None or consolidated.document_type != "STATUTE":
                    raise StatuteVersionChainError("合并全文必须是已核验的法规全文成员")

            chain = StatuteVersionChain(
                law_slug=law_slug,
                target_version_id=target_version_id,
                effective_from=effective_from,
                effective_to=effective_to,
                consolidated_source_import_id=consolidated_source_import_id,
            )
            session.add(chain)
            session.flush()
            for sequence, member in enumerate(members, start=1):
                session.add(
                    StatuteVersionChainMember(
                        chain_id=chain.id,
                        source_import_id=int(member["source_import_id"]),
                        sequence=sequence,
                        role=str(member["role"]),
                    )
                )
            session.commit()
            session.refresh(chain)
            return self._serialize(session, chain)

    def list_chains(self) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            chains = session.scalars(
                select(StatuteVersionChain).order_by(
                    StatuteVersionChain.law_slug,
                    StatuteVersionChain.effective_from,
                    StatuteVersionChain.id,
                )
            ).all()
            return [self._serialize(session, chain) for chain in chains]

    def list_chains_for_law(self, law_slug: str) -> list[dict[str, Any]]:
        """Return one law's registered version timeline in chronological order."""
        with self._session_factory() as session:
            chains = session.scalars(
                select(StatuteVersionChain)
                .where(StatuteVersionChain.law_slug == law_slug)
                .order_by(StatuteVersionChain.effective_from, StatuteVersionChain.id)
            ).all()
            return [self._serialize(session, chain) for chain in chains]

    def attach_consolidated_source(
        self, chain_id: int, *, source_import_id: int
    ) -> dict[str, Any]:
        """Attach one verified, same-law consolidated statute to an incomplete chain."""
        with self._session_factory() as session:
            chain = session.get(StatuteVersionChain, chain_id)
            if chain is None:
                raise StatuteVersionChainError("版本链不存在")
            source = session.get(LegalSourceImport, source_import_id)
            if source is None:
                raise StatuteVersionChainError("合并全文来源不存在")
            if source.law_slug != chain.law_slug:
                raise StatuteVersionChainError("合并全文必须属于同一法律")
            if source.document_type != "STATUTE":
                raise StatuteVersionChainError("合并全文必须是法规全文")
            if source.authority_status != "VERIFIED" or not source.authority_url:
                raise StatuteVersionChainError("合并全文尚未完成权威核验")

            member = session.scalar(
                select(StatuteVersionChainMember).where(
                    StatuteVersionChainMember.chain_id == chain.id,
                    StatuteVersionChainMember.source_import_id == source.id,
                )
            )
            if member is None:
                last_sequence = session.scalar(
                    select(func.max(StatuteVersionChainMember.sequence)).where(
                        StatuteVersionChainMember.chain_id == chain.id
                    )
                )
                session.add(
                    StatuteVersionChainMember(
                        chain_id=chain.id,
                        source_import_id=source.id,
                        sequence=(last_sequence or 0) + 1,
                        role="CONSOLIDATED_TEXT",
                    )
                )
            else:
                member.role = "CONSOLIDATED_TEXT"
            chain.consolidated_source_import_id = source.id
            session.commit()
            session.refresh(chain)
            return self._serialize(session, chain)

    def get_index_provenance(self, chain_id: int, *, as_of: date) -> dict[str, str]:
        """Return Chroma-safe provenance only for an effective, complete version chain."""
        with self._session_factory() as session:
            chain = session.get(StatuteVersionChain, chain_id)
            if chain is None:
                raise StatuteVersionChainError("版本链不存在")
            payload = self._serialize(session, chain)
            if not payload["is_indexable"]:
                raise StatuteVersionChainError(str(payload["index_block_reason"]))
            if as_of < chain.effective_from or (
                chain.effective_to is not None and as_of > chain.effective_to
            ):
                raise StatuteVersionChainError("VERSION_NOT_EFFECTIVE_ON_QUERY_DATE")
            source = session.get(LegalSourceImport, chain.consolidated_source_import_id)
            if source is None or not source.authority_url:
                raise StatuteVersionChainError("CONSOLIDATED_TEXT_UNVERIFIED")
            return {
                "version_id": chain.target_version_id,
                "effective_from": chain.effective_from.isoformat(),
                "effective_to": chain.effective_to.isoformat() if chain.effective_to else "",
                "source_url": source.authority_url,
                "content_hash": source.content_sha256,
            }

    def get_indexable_chain_for_law(self, law_slug: str, *, as_of: date) -> dict[str, Any]:
        """Select exactly one complete version that is effective on ``as_of``."""
        with self._session_factory() as session:
            chains = session.scalars(
                select(StatuteVersionChain)
                .where(
                    StatuteVersionChain.law_slug == law_slug,
                    StatuteVersionChain.effective_from <= as_of,
                    (StatuteVersionChain.effective_to.is_(None))
                    | (StatuteVersionChain.effective_to >= as_of),
                )
                .order_by(StatuteVersionChain.effective_from.desc(), StatuteVersionChain.id.desc())
            ).all()
            eligible = [
                payload
                for payload in (self._serialize(session, chain) for chain in chains)
                if payload["is_indexable"]
            ]
            if not eligible:
                raise StatuteVersionChainError("NO_INDEXABLE_VERSION_ON_QUERY_DATE")
            if len(eligible) != 1:
                raise StatuteVersionChainError("AMBIGUOUS_EFFECTIVE_VERSION")
            return eligible[0]

    @staticmethod
    def _serialize(session: Session, chain: StatuteVersionChain) -> dict[str, Any]:
        members = session.execute(
            select(StatuteVersionChainMember, LegalSourceImport)
            .join(
                LegalSourceImport,
                LegalSourceImport.id == StatuteVersionChainMember.source_import_id,
            )
            .where(StatuteVersionChainMember.chain_id == chain.id)
            .order_by(StatuteVersionChainMember.sequence)
        ).all()
        consolidated = (
            next((source for member, source in members if source.id == chain.consolidated_source_import_id), None)
            if chain.consolidated_source_import_id is not None
            else None
        )
        reason = None
        if consolidated is None:
            reason = "CONSOLIDATED_TEXT_REQUIRED"
        elif consolidated.authority_status != "VERIFIED":
            reason = "CONSOLIDATED_TEXT_UNVERIFIED"
        elif consolidated.source_status == "PUBLISHED_NOT_EFFECTIVE":
            reason = "VERSION_NOT_EFFECTIVE"
        return {
            "id": chain.id,
            "law_slug": chain.law_slug,
            "target_version_id": chain.target_version_id,
            "effective_from": chain.effective_from.isoformat(),
            "effective_to": chain.effective_to.isoformat() if chain.effective_to else None,
            "consolidated_source_import_id": chain.consolidated_source_import_id,
            "is_indexable": reason is None,
            "index_block_reason": reason,
            "members": [
                {
                    "source_import_id": source.id,
                    "version_id": source.version_id,
                    "role": member.role,
                    "document_type": source.document_type,
                }
                for member, source in members
            ],
        }
