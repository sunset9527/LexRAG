"""v2.2 场景任务服务：数据库层只保存受控、可追溯的结构化结果。"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from app.models.scenario_job import ScenarioJob
from src.scenarios.legal_scenarios import (
    DISCLAIMER,
    build_document_draft,
    build_rights_path,
    build_rights_path_graph,
    check_compliance,
    detect_contract_risks,
    split_contract_clauses,
)
from src.workflow.evidence import CitationVerifier, EvidenceItem, EvidenceLedger


class ScenarioService:
    ALLOWED_TYPES = {"contract_review", "compliance_check", "document_draft", "rights_path"}

    def __init__(
        self,
        session_factory: Callable[[], Any],
        evidence_provider: Callable[..., list[dict[str, Any]]] | None = None,
        advice_generator: Callable[[str, list[str]], str] | None = None,
        case_provider: Callable[[str], list[dict[str, Any]]] | None = None,
    ):
        self._session_factory = session_factory
        self._evidence_provider = evidence_provider
        self._advice_generator = advice_generator
        self._case_provider = case_provider

    @staticmethod
    def _to_dict(job: ScenarioJob) -> dict[str, Any]:
        return {
            "id": job.id,
            "scenario_type": job.scenario_type,
            "input_data": job.input_data,
            "result_data": job.result_data,
            "status": job.status,
            "error_message": job.error_message,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        }

    def create(
        self,
        *,
        user_id: int,
        scenario_type: str,
        input_data: dict[str, Any],
        organization_id: int | None = None,
    ) -> dict[str, Any]:
        if scenario_type not in self.ALLOWED_TYPES:
            raise ValueError("不支持的法律场景")
        with self._session_factory() as db:
            job = ScenarioJob(
                id=str(uuid.uuid4()),
                user_id=user_id,
                organization_id=organization_id,
                scenario_type=scenario_type,
                input_data=input_data,
                status="PENDING",
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            return self._to_dict(job)

    def list_for_user(
        self, *, user_id: int, organization_id: int | None = None
    ) -> list[dict[str, Any]]:
        with self._session_factory() as db:
            query = db.query(ScenarioJob).filter(ScenarioJob.user_id == user_id)
            if organization_id is not None:
                query = query.filter(ScenarioJob.organization_id == organization_id)
            jobs = query.order_by(ScenarioJob.created_at.desc()).all()
            return [self._to_dict(job) for job in jobs]

    def get(
        self, *, user_id: int, scenario_id: str, organization_id: int | None = None
    ) -> dict[str, Any] | None:
        with self._session_factory() as db:
            query = db.query(ScenarioJob).filter(
                ScenarioJob.id == scenario_id, ScenarioJob.user_id == user_id
            )
            if organization_id is not None:
                query = query.filter(ScenarioJob.organization_id == organization_id)
            job = query.first()
            return self._to_dict(job) if job else None

    def process(
        self, *, user_id: int, scenario_id: str, organization_id: int | None = None
    ) -> dict[str, Any] | None:
        with self._session_factory() as db:
            query = db.query(ScenarioJob).filter(
                ScenarioJob.id == scenario_id, ScenarioJob.user_id == user_id
            )
            if organization_id is not None:
                query = query.filter(ScenarioJob.organization_id == organization_id)
            job = query.first()
            if job is None:
                return None
            job.status = "PROCESSING"
            job.error_message = None
            db.commit()
            try:
                job.result_data = self._run(job.scenario_type, job.input_data)
                job.status = "READY"
            except Exception as exc:
                job.status = "FAILED"
                job.error_message = type(exc).__name__
            db.commit()
            db.refresh(job)
            return self._to_dict(job)

    def generate_contract_advice(
        self, *, user_id: int, scenario_id: str, organization_id: int | None = None
    ) -> dict[str, Any] | None:
        """在任务完成后，以本次已验证证据生成建议；调用方持有临时密钥。"""
        if self._advice_generator is None:
            raise ValueError("未配置运行时模型，无法生成修改建议")
        with self._session_factory() as db:
            query = db.query(ScenarioJob).filter(
                ScenarioJob.id == scenario_id, ScenarioJob.user_id == user_id
            )
            if organization_id is not None:
                query = query.filter(ScenarioJob.organization_id == organization_id)
            job = query.first()
            if job is None:
                return None
            if job.scenario_type != "contract_review" or job.status != "READY":
                raise ValueError("仅可为已完成的合同审查任务生成建议")
            result = dict(job.result_data or {})
            findings = list(result.get("findings", []))
            for finding in findings:
                if (
                    isinstance(finding, dict)
                    and finding.get("evidence_status") == "verified"
                    and finding.get("citations")
                    and not finding.get("advice")
                ):
                    finding["advice"] = self._advice_generator(
                        str(finding.get("clause_text", "")),
                        list(finding["citations"]),
                    )
            result["findings"] = findings
            job.result_data = result
            db.commit()
            db.refresh(job)
            return self._to_dict(job)

    def _run(self, scenario_type: str, data: dict[str, Any]) -> dict[str, Any]:
        if scenario_type == "contract_review":
            clauses = split_contract_clauses(str(data.get("text", "")))
            if not clauses:
                raise ValueError("未提取到可审查条款")
            findings = []
            for item in detect_contract_risks(clauses):
                payload = item.to_dict()
                payload.update(self._evidence_for(item.clause_text))
                payload["case_evidence"] = (
                    self._case_provider(item.clause_text) if self._case_provider else []
                )
                if payload["evidence_status"] == "verified" and self._advice_generator:
                    payload["advice"] = self._advice_generator(
                        item.clause_text, payload["citations"]
                    )
                findings.append(payload)
            return {
                "clauses": [item.__dict__ for item in clauses],
                "findings": findings,
                "evidence_status": "verified"
                if any(item["evidence_status"] == "verified" for item in findings)
                else "not_retrieved",
                "disclaimer": DISCLAIMER,
            }
        if scenario_type == "compliance_check":
            domain = str(data.get("domain", ""))
            findings = []
            for item in check_compliance(str(data.get("text", "")), domain=domain):
                payload = item.to_dict()
                payload.update(self._evidence_for(item.evidence_query, item.knowledge_base_slug))
                findings.append(payload)
            return {
                "domain": domain,
                "findings": findings,
                "evidence_status": "verified"
                if any(item["evidence_status"] == "verified" for item in findings)
                else "not_retrieved",
                "disclaimer": DISCLAIMER,
            }
        if scenario_type == "document_draft":
            draft = build_document_draft(
                str(data.get("template", "")), dict(data.get("fields", {}))
            )
            return {**draft, **self._evidence_for(draft["content"]), "disclaimer": DISCLAIMER}
        if scenario_type == "rights_path":
            dispute_type = str(data.get("dispute_type", ""))
            path = build_rights_path(dispute_type)
            if not path:
                raise ValueError("不支持的纠纷类型")
            graph = build_rights_path_graph(dispute_type)
            knowledge_base_slug = path[0]["knowledge_base_slug"]
            return {
                "dispute_type": dispute_type,
                "path": path,
                "graph": graph,
                **self._evidence_for(f"{dispute_type} 维权流程", knowledge_base_slug),
                "disclaimer": DISCLAIMER,
            }
        raise ValueError("不支持的法律场景")

    def _evidence_for(self, query: str, knowledge_base_slug: str = "civil-code") -> dict[str, Any]:
        if self._evidence_provider is None:
            return {"evidence_status": "not_retrieved", "citations": []}
        ledger = EvidenceLedger()
        try:
            raw_items = self._evidence_provider(query, knowledge_base_slug) or []
        except TypeError:
            # 兼容旧的单参数提供器；最终仍按目标知识库过滤，避免跨库引用。
            raw_items = self._evidence_provider(query) or []
        for raw in raw_items:
            item = EvidenceItem(
                source_id=str(raw.get("source_id", "")),
                source_type="statute",
                knowledge_base_slug=str(raw.get("knowledge_base_slug", knowledge_base_slug)),
                law_name=str(raw.get("law_name", "")),
                article_id=str(raw.get("article_id", "")),
                content=str(raw.get("content", "")),
                score=float(raw.get("score", 0)),
                retrieval_path="scenario",
            )
            ledger.add(item)
        statutes = ledger.statutes_for(knowledge_base_slug)
        citations = [f"【{item.law_name}第{item.normalized_article_id}条】" for item in statutes]
        if not citations:
            return {"evidence_status": "not_retrieved", "citations": []}
        verification = CitationVerifier().verify(
            "\n".join(citations), ledger, knowledge_base_slug=knowledge_base_slug
        )
        return {
            "evidence_status": "verified" if verification.status == "pass" else "not_retrieved",
            "citations": citations if verification.status == "pass" else [],
        }
