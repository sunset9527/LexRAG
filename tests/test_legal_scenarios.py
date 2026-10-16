"""v2.2 法律场景的核心契约：所有结论均可回溯，且不会补造事实。"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import FastAPI

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.scenarios.legal_scenarios import (  # noqa: E402, I001
    DOCUMENT_TEMPLATES,
    build_structured_report,
    build_rights_path,
    build_rights_path_graph,
    build_scenario_pdf,
    check_compliance,
    detect_contract_risks,
    split_contract_clauses,
    validate_document_fields,
)


def test_contract_clause_split_and_four_risk_types_are_traceable():
    clauses = split_contract_clauses(
        "第一条 违约责任\n乙方违约金按每日合同总价10%支付。\n"
        "第二条 免责\n甲方对任何损失概不负责。\n"
        "第三条 格式条款\n本公司有权单方解释和修改本合同。\n"
        "第四条 争议解决\n由甲方所在地人民法院管辖。"
    )

    findings = detect_contract_risks(clauses)

    assert [clause.position for clause in clauses] == ["第1条", "第2条", "第3条", "第4条"]
    assert {item.risk_type for item in findings} == {
        "liquidated_damages",
        "exemption",
        "format_terms",
        "jurisdiction",
    }
    assert all(item.clause_position.startswith("第") for item in findings)
    assert all(item.status == "review" for item in findings)


def test_compliance_and_rights_path_are_controlled_not_freeform():
    results = check_compliance(
        "公司规定员工自愿放弃社会保险，并且不支付加班费。",
        domain="labor",
    )
    path = build_rights_path("labor")

    assert {item.rule_id for item in results} == {"social_insurance", "overtime_pay"}
    assert all(item.status == "risk" for item in results)
    assert [node["stage"] for node in path] == ["协商", "投诉", "仲裁", "诉讼"]
    assert build_rights_path("unknown") == []


def test_compliance_rules_and_rights_graph_keep_legal_scope_and_transition_data():
    findings = check_compliance("公司规定员工自愿放弃社会保险。", domain="labor")
    graph = build_rights_path_graph("labor")

    assert findings[0].knowledge_base_slug == "labor-law"
    assert "社会保险" in findings[0].evidence_query
    assert graph["dispute_type"] == "labor"
    assert [node["id"] for node in graph["nodes"]] == [
        "labor-negotiation",
        "labor-complaint",
        "labor-arbitration",
        "labor-litigation",
    ]
    assert graph["edges"][-1] == {
        "from": "labor-arbitration",
        "to": "labor-litigation",
        "condition": "对仲裁裁决不服或法律允许直接起诉",
    }
    assert all(node["knowledge_base_slug"] == "labor-law" for node in graph["nodes"])


def test_document_template_rejects_missing_required_facts_and_keeps_submitted_facts_only():
    template = DOCUMENT_TEMPLATES["arbitration_application"]

    assert validate_document_fields(template, {"applicant": "张三"}) == [
        "respondent",
        "claims",
        "facts",
    ]
    assert (
        validate_document_fields(
            template,
            {
                "applicant": "张三",
                "respondent": "某公司",
                "claims": "支付工资",
                "facts": "拖欠工资",
            },
        )
        == []
    )


def test_pdf_export_returns_a_valid_pdf_with_disclaimer():
    pdf = build_scenario_pdf(
        "合同审查报告",
        [{"title": "高风险条款", "content": "需人工核验"}],
    )

    assert pdf.startswith(b"%PDF-")
    assert b"LexRAG" in pdf


def test_structured_report_separates_risk_statute_case_and_suggestion_sections():
    report = build_structured_report(
        "contract_review",
        {
            "evidence_status": "verified",
            "findings": [
                {
                    "risk_type": "exemption",
                    "severity": "high",
                    "reason": "免责约定需要核验。",
                    "citations": ["【中华人民共和国民法典第506条】"],
                    "case_evidence": [{"case_id": "annual-1", "title": "案例", "summary": "摘要"}],
                    "advice": "删除绝对免责表述。",
                }
            ],
            "disclaimer": "仅供参考",
        },
    )

    assert report["title"] == "合同审查报告"
    assert [section["title"] for section in report["sections"]] == [
        "处理摘要",
        "风险与核验项目",
        "法条依据",
        "参考案例",
        "修改建议",
        "使用提示",
    ]
    assert "第506条" in report["sections"][2]["content"]
    assert "annual-1" in report["sections"][3]["content"]


def test_contract_review_attaches_only_current_retrieved_statute_evidence():
    from app.services.scenario_service import ScenarioService

    service = ScenarioService(
        lambda: None,
        evidence_provider=lambda query: [
            {
                "law_name": "中华人民共和国民法典",
                "article_id": "506",
                "content": "合同中的下列免责条款无效。",
                "source_id": "civil-506",
            }
        ],
    )

    result = service._run("contract_review", {"text": "第一条 甲方对任何损失概不负责。"})

    finding = result["findings"][0]
    assert finding["evidence_status"] == "verified"
    assert finding["citations"] == ["【中华人民共和国民法典第506条】"]


def test_compliance_review_uses_the_same_evidence_gate():
    from app.services.scenario_service import ScenarioService

    service = ScenarioService(
        lambda: None,
        evidence_provider=lambda query: [
            {
                "law_name": "中华人民共和国劳动法",
                "article_id": "44",
                "content": "延长工作时间的工资报酬。",
                "source_id": "labor-44",
            }
        ],
    )
    result = service._run("compliance_check", {"domain": "labor", "text": "公司规定不支付加班费。"})

    assert result["findings"][0]["evidence_status"] == "verified"
    assert result["findings"][0]["citations"] == ["【中华人民共和国劳动法第44条】"]


def test_compliance_evidence_is_rejected_when_it_belongs_to_another_knowledge_base():
    from app.services.scenario_service import ScenarioService

    service = ScenarioService(
        lambda: None,
        evidence_provider=lambda query, slug: [
            {
                "law_name": "中华人民共和国民法典",
                "article_id": "577",
                "content": "当事人一方不履行合同义务。",
                "source_id": "civil-577",
                "knowledge_base_slug": "civil-code",
            }
        ],
    )

    result = service._run("compliance_check", {"domain": "labor", "text": "公司规定不支付加班费。"})

    assert result["findings"][0]["evidence_status"] == "not_retrieved"
    assert result["findings"][0]["citations"] == []


def test_document_and_rights_path_expose_only_verified_citations():
    from app.services.scenario_service import ScenarioService

    service = ScenarioService(
        lambda: None,
        evidence_provider=lambda query: [
            {
                "law_name": "中华人民共和国民法典",
                "article_id": "577",
                "content": "当事人一方不履行合同义务。",
                "source_id": "civil-577",
            }
        ],
    )
    document = service._run(
        "document_draft",
        {
            "template": "complaint",
            "fields": {
                "plaintiff": "张三",
                "defendant": "李四",
                "claims": "继续履行",
                "facts": "合同到期未履行",
            },
        },
    )
    path = service._run("rights_path", {"dispute_type": "contract"})

    assert document["evidence_status"] == "verified"
    assert document["citations"] == ["【中华人民共和国民法典第577条】"]
    assert path["evidence_status"] == "verified"
    assert path["citations"] == ["【中华人民共和国民法典第577条】"]


def test_contract_advice_is_generated_only_after_evidence_verification():
    from app.services.scenario_service import ScenarioService

    calls = []
    service = ScenarioService(
        lambda: None,
        evidence_provider=lambda query: [
            {
                "law_name": "中华人民共和国民法典",
                "article_id": "506",
                "content": "合同中的下列免责条款无效。",
                "source_id": "civil-506",
            }
        ],
        advice_generator=lambda clause, citations: (
            calls.append((clause, citations)) or "建议明确责任范围并删除绝对免责表述。"
        ),
    )

    result = service._run("contract_review", {"text": "第一条 甲方对任何损失概不负责。"})

    assert result["findings"][0]["advice"] == "建议明确责任范围并删除绝对免责表述。"
    assert calls[0][1] == ["【中华人民共和国民法典第506条】"]


def test_ready_contract_can_generate_advice_later_without_persisting_runtime_key():
    from app.services.scenario_service import ScenarioService

    job = SimpleNamespace(
        id="scenario-1",
        user_id=7,
        scenario_type="contract_review",
        input_data={},
        status="READY",
        error_message=None,
        created_at=None,
        updated_at=None,
        result_data={
            "findings": [
                {
                    "clause_text": "甲方概不负责。",
                    "evidence_status": "verified",
                    "citations": ["【中华人民共和国民法典第506条】"],
                }
            ]
        },
    )

    class Session:
        def query(self, model):
            return self

        def filter(self, *args):
            return self

        def first(self):
            return job

        def commit(self):
            pass

        def refresh(self, value):
            pass

    class SessionContext:
        def __enter__(self):
            return Session()

        def __exit__(self, *args):
            return False

    service = ScenarioService(
        SessionContext,
        advice_generator=lambda clause, citations: "删除绝对免责表述。",
    )
    result = service.generate_contract_advice(user_id=7, scenario_id="scenario-1")

    assert result["result_data"]["findings"][0]["advice"] == "删除绝对免责表述。"


def test_contract_review_keeps_case_evidence_separate_from_statute_citations():
    from app.services.scenario_service import ScenarioService

    service = ScenarioService(
        lambda: None,
        evidence_provider=lambda query: [
            {
                "law_name": "中华人民共和国民法典",
                "article_id": "506",
                "content": "免责条款。",
                "source_id": "civil-506",
            }
        ],
        case_provider=lambda query: [
            {"case_id": "annual-1", "summary": "年度案例中的免责条款争议摘要。", "score": 0.8}
        ],
    )

    result = service._run("contract_review", {"text": "第一条 甲方对任何损失概不负责。"})

    assert result["findings"][0]["citations"] == ["【中华人民共和国民法典第506条】"]
    assert result["findings"][0]["case_evidence"] == [
        {"case_id": "annual-1", "summary": "年度案例中的免责条款争议摘要。", "score": 0.8}
    ]


def test_scenario_routes_bind_requests_to_authenticated_user(monkeypatch):
    from app.api import scenarios

    class FakeScenarioService:
        def __init__(self):
            self.created = None

        def create(self, **kwargs):
            self.created = kwargs
            return {"id": "scenario-1", "status": "PENDING", **kwargs}

        def get(self, *, user_id, scenario_id, organization_id=None):
            return {"id": scenario_id, "user_id": user_id, "status": "READY"}

        def process(self, *, user_id, scenario_id, organization_id=None):
            return {"id": scenario_id, "user_id": user_id, "status": "READY"}

        def list_for_user(self, *, user_id, organization_id=None):
            return [{"id": "scenario-1", "user_id": user_id}]

        def generate_contract_advice(self, *, user_id, scenario_id, organization_id=None):
            return {"id": scenario_id, "user_id": user_id, "status": "READY", "advice": "已生成"}

    fake = FakeScenarioService()
    dispatched = []
    app = FastAPI()
    app.include_router(scenarios.router)
    app.dependency_overrides[scenarios.get_current_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[scenarios.get_authorization_context] = lambda: SimpleNamespace(
        organization_id=1
    )
    monkeypatch.setattr(scenarios, "_service", lambda *args, **kwargs: fake)
    monkeypatch.setattr(
        scenarios.process_scenario_task,
        "delay",
        lambda user_id, scenario_id, organization_id: dispatched.append(
            (user_id, scenario_id, organization_id)
        ),
    )

    async def request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/scenarios",
                json={"scenario_type": "rights_path", "input_data": {"dispute_type": "labor"}},
            )
            listed = await client.get("/scenarios")
            detail = await client.get("/scenarios/scenario-1")
            advice = await client.post(
                "/scenarios/scenario-1/advice", headers={"X-API-Key": "runtime-key"}
            )
            return created, listed, detail, advice

    created, listed, detail, advice = asyncio.run(request())

    assert created.status_code == 201
    assert fake.created["user_id"] == 7
    assert dispatched == [(7, "scenario-1", 1)]
    assert listed.json()["items"] == [{"id": "scenario-1", "user_id": 7}]
    assert detail.json()["user_id"] == 7
    assert advice.status_code == 200
    assert advice.json()["advice"] == "已生成"


def test_scenario_celery_task_uses_runtime_service_without_a_user_api_key(monkeypatch):
    from app.tasks import scenario_tasks

    calls = []
    monkeypatch.setattr(scenario_tasks, "init_db", lambda: calls.append("init_db"))
    monkeypatch.setattr(scenario_tasks.db_session, "SessionLocal", None)
    monkeypatch.setattr(
        scenario_tasks,
        "create_runtime_scenario_service",
        lambda: SimpleNamespace(
            process=lambda **kwargs: calls.append(kwargs) or {"status": "READY"}
        ),
    )

    result = scenario_tasks.process_scenario_task(7, "scenario-1")

    assert result == {"status": "READY"}
    assert calls == [
        "init_db",
        {"user_id": 7, "scenario_id": "scenario-1", "organization_id": None},
    ]
