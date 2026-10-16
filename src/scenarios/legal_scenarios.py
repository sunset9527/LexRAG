"""可解释、可测试的 v2.2 场景规则；不在此层生成法律结论。"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

DISCLAIMER = "本系统提供法律信息参考，不构成法律建议；请结合完整事实咨询专业律师。"


@dataclass(frozen=True)
class ContractClause:
    number: str
    title: str
    text: str
    position: str


@dataclass(frozen=True)
class RiskFinding:
    risk_type: str
    severity: str
    status: str
    clause_position: str
    clause_text: str
    reason: str
    evidence_status: str = "pending"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class ComplianceFinding:
    rule_id: str
    severity: str
    status: str
    reason: str
    knowledge_base_slug: str
    evidence_query: str
    evidence_status: str = "pending"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


_ARTICLE = re.compile(r"^第([一二三四五六七八九十百千万\d]+)条\s*(.*)$")


def _arabic_number(value: str) -> str:
    if value.isdigit():
        return value
    digits = {
        "零": 0,
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    units = {"十": 10, "百": 100, "千": 1000, "万": 10000}
    total = current = 0
    for char in value:
        if char in digits:
            current = digits[char]
        elif char in units:
            current = (current or 1) * units[char]
            total += current
            current = 0
    return str(total + current) if total + current else value


def split_contract_clauses(text: str) -> list[ContractClause]:
    """以条号为首选边界；无条号内容也保留为“前言”，避免静默丢失。"""
    clauses: list[ContractClause] = []
    current_number = "前言"
    current_title = "未编号内容"
    current_lines: list[str] = []

    def flush() -> None:
        body = "\n".join(current_lines).strip()
        if body:
            position = "前言" if current_number == "前言" else f"第{current_number}条"
            clauses.append(ContractClause(current_number, current_title, body, position))

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _ARTICLE.match(line)
        if match:
            flush()
            current_number = _arabic_number(match.group(1))
            current_title = match.group(2).strip() or "未命名条款"
            current_lines = [line]
        else:
            current_lines.append(line)
    flush()
    return clauses


_CONTRACT_RULES = (
    (
        "liquidated_damages",
        "high",
        ("违约金", "每日合同总价", "按日"),
        "违约责任的计算方式或比例需要结合损失与交易情况核验。",
    ),
    (
        "exemption",
        "high",
        ("概不负责", "不承担任何责任", "全部免责"),
        "免责约定可能限制一方责任，需核验其适用范围与效力。",
    ),
    (
        "format_terms",
        "medium",
        ("单方解释", "单方修改", "单方变更"),
        "单方解释或变更表述可能影响格式条款公平性，需人工核验。",
    ),
    (
        "jurisdiction",
        "medium",
        ("所在地人民法院管辖", "由甲方所在地法院管辖", "专属管辖"),
        "争议解决地点可能增加维权成本，应结合双方约定核验。",
    ),
)


def detect_contract_risks(clauses: list[ContractClause]) -> list[RiskFinding]:
    findings: list[RiskFinding] = []
    for clause in clauses:
        for risk_type, severity, triggers, reason in _CONTRACT_RULES:
            if any(trigger in clause.text for trigger in triggers):
                findings.append(
                    RiskFinding(risk_type, severity, "review", clause.position, clause.text, reason)
                )
    return findings


_COMPLIANCE_RULES = {
    "labor": (
        (
            "social_insurance",
            "high",
            ("放弃社会保险", "不缴纳社会保险"),
            "制度含有社会保险权利限制表述，需人工核验。",
            "劳动法 用人单位 社会保险 义务",
        ),
        (
            "overtime_pay",
            "high",
            ("不支付加班费", "免费加班"),
            "制度含有加班报酬限制表述，需人工核验。",
            "劳动法 延长工作时间 工资报酬",
        ),
    ),
    "company": (
        (
            "capital_withdrawal",
            "high",
            ("抽逃出资", "退还出资"),
            "文本涉及出资返还或抽逃表述，需人工核验。",
            "公司法 抽逃出资 法律责任",
        ),
        (
            "shareholder_resolution",
            "medium",
            ("无需股东会", "免经股东会"),
            "文本可能绕开公司决议程序，需人工核验。",
            "公司法 股东会 决议 程序",
        ),
    ),
}

_DOMAIN_KNOWLEDGE_BASES = {"labor": "labor-law", "company": "company-law"}


def check_compliance(text: str, *, domain: str) -> list[ComplianceFinding]:
    return [
        ComplianceFinding(
            rule_id,
            severity,
            "risk",
            reason,
            _DOMAIN_KNOWLEDGE_BASES[domain],
            evidence_query,
        )
        for rule_id, severity, triggers, reason, evidence_query in _COMPLIANCE_RULES.get(domain, ())
        if any(trigger in text for trigger in triggers)
    ]


DOCUMENT_TEMPLATES: dict[str, dict[str, Any]] = {
    "complaint": {
        "name": "民事起诉状",
        "required_fields": ["plaintiff", "defendant", "claims", "facts"],
    },
    "defense": {
        "name": "民事答辩状",
        "required_fields": ["defendant", "plaintiff", "defense", "facts"],
    },
    "arbitration_application": {
        "name": "仲裁申请书",
        "required_fields": ["applicant", "respondent", "claims", "facts"],
    },
    "lawyer_letter": {
        "name": "律师函草稿",
        "required_fields": ["sender", "recipient", "facts", "request"],
    },
    "contract": {
        "name": "合同草稿",
        "required_fields": ["party_a", "party_b", "subject_matter", "rights_obligations"],
    },
}


def validate_document_fields(template: dict[str, Any], data: dict[str, Any]) -> list[str]:
    return [field for field in template["required_fields"] if not str(data.get(field, "")).strip()]


def build_document_draft(template_key: str, data: dict[str, Any]) -> dict[str, Any]:
    template = DOCUMENT_TEMPLATES.get(template_key)
    if template is None:
        raise ValueError("不支持的文书类型")
    missing = validate_document_fields(template, data)
    if missing:
        raise ValueError("缺少必填事实：" + "、".join(missing))
    fields = {key: str(data[key]).strip() for key in template["required_fields"]}
    lines = [template["name"], ""] + [f"{key}：{value}" for key, value in fields.items()]
    lines.extend(["", "以上内容仅根据提交信息生成，需人工补充和核验。", DISCLAIMER])
    return {
        "document_type": template_key,
        "title": template["name"],
        "content": "\n".join(lines),
        "fields": fields,
    }


_RIGHTS_PATHS: dict[str, list[dict[str, str]]] = {
    "labor": [
        {
            "id": "labor-negotiation",
            "stage": "协商",
            "condition": "确认劳动关系与争议事项",
            "materials": "劳动合同、工资记录、沟通记录",
            "action": "向用人单位提出书面协商请求",
            "knowledge_base_slug": "labor-law",
            "evidence_query": "劳动争议 协商 证据材料",
        },
        {
            "id": "labor-complaint",
            "stage": "投诉",
            "condition": "涉及劳动保障监察事项",
            "materials": "身份证明、劳动关系与事实材料",
            "action": "向劳动保障监察机构咨询或投诉",
            "knowledge_base_slug": "labor-law",
            "evidence_query": "劳动保障监察 投诉 材料",
        },
        {
            "id": "labor-arbitration",
            "stage": "仲裁",
            "condition": "劳动争议通常需先仲裁",
            "materials": "仲裁申请书及证据目录",
            "action": "向有管辖权的劳动人事争议仲裁机构申请",
            "knowledge_base_slug": "labor-law",
            "evidence_query": "劳动争议 仲裁 前置 程序",
        },
        {
            "id": "labor-litigation",
            "stage": "诉讼",
            "condition": "对仲裁裁决不服或法律允许直接起诉",
            "materials": "仲裁材料、证据与身份材料",
            "action": "在法定期限内向有管辖权法院咨询或起诉",
            "knowledge_base_slug": "labor-law",
            "evidence_query": "劳动争议 仲裁裁决 诉讼",
        },
    ],
    "contract": [
        {
            "id": "contract-negotiation",
            "stage": "协商",
            "condition": "先固定合同和履行事实",
            "materials": "合同、付款凭证、往来记录",
            "action": "提出明确履行、整改或赔偿请求",
            "knowledge_base_slug": "civil-code",
            "evidence_query": "合同纠纷 协商 履行 证据",
        },
        {
            "id": "contract-mediation",
            "stage": "调解",
            "condition": "双方同意第三方协助",
            "materials": "争议事实与证据清单",
            "action": "选择行业、商事或人民调解渠道",
            "knowledge_base_slug": "civil-code",
            "evidence_query": "合同纠纷 调解",
        },
        {
            "id": "contract-arbitration",
            "stage": "仲裁",
            "condition": "合同中存在有效仲裁约定",
            "materials": "仲裁协议、合同与证据",
            "action": "向约定仲裁机构申请",
            "knowledge_base_slug": "civil-code",
            "evidence_query": "仲裁协议 有效 仲裁",
        },
        {
            "id": "contract-litigation",
            "stage": "诉讼",
            "condition": "无有效仲裁约定或法律允许",
            "materials": "起诉状、合同与证据",
            "action": "向有管辖权法院咨询或起诉",
            "knowledge_base_slug": "civil-code",
            "evidence_query": "合同纠纷 管辖 诉讼",
        },
    ],
    "tort": [
        {
            "id": "tort-negotiation",
            "stage": "协商",
            "condition": "先固定侵权和损失证据",
            "materials": "现场记录、医疗或财产损失凭证",
            "action": "向相关责任方提出协商",
            "knowledge_base_slug": "civil-code",
            "evidence_query": "侵权责任 证据 损失",
        },
        {
            "id": "tort-complaint",
            "stage": "投诉",
            "condition": "存在行业监管或消费者争议渠道",
            "materials": "交易和损失材料",
            "action": "向对应监管或调解渠道咨询",
            "knowledge_base_slug": "civil-code",
            "evidence_query": "消费者 侵权 投诉",
        },
        {
            "id": "tort-mediation",
            "stage": "调解",
            "condition": "双方愿意调解",
            "materials": "责任与损失材料",
            "action": "申请人民或行业调解",
            "knowledge_base_slug": "civil-code",
            "evidence_query": "侵权纠纷 调解",
        },
        {
            "id": "tort-litigation",
            "stage": "诉讼",
            "condition": "协商调解未果",
            "materials": "起诉状、证据与损失计算材料",
            "action": "向有管辖权法院咨询或起诉",
            "knowledge_base_slug": "civil-code",
            "evidence_query": "侵权责任 诉讼 管辖",
        },
    ],
}


def build_rights_path(dispute_type: str) -> list[dict[str, str]]:
    return [dict(node) for node in _RIGHTS_PATHS.get(dispute_type, [])]


def build_rights_path_graph(dispute_type: str) -> dict[str, Any]:
    """返回受控流程图，不根据模型输出擅自新增救济步骤。"""
    nodes = build_rights_path(dispute_type)
    return {
        "dispute_type": dispute_type,
        "nodes": nodes,
        "edges": [
            {"from": previous["id"], "to": current["id"], "condition": current["condition"]}
            for previous, current in zip(nodes, nodes[1:], strict=False)
        ],
    }


_SCENARIO_REPORT_TITLES = {
    "contract_review": "合同审查报告",
    "compliance_check": "合规检查报告",
    "document_draft": "法律文书草稿报告",
    "rights_path": "维权路径报告",
}


def build_structured_report(scenario_type: str, result: dict[str, Any]) -> dict[str, Any]:
    """将受控任务结果整理成可下载的报告章节，不渲染原始 JSON。"""
    title = _SCENARIO_REPORT_TITLES.get(scenario_type, "法律场景报告")
    findings = result.get("findings") if isinstance(result.get("findings"), list) else []
    citations: list[str] = []
    case_lines: list[str] = []
    advice_lines: list[str] = []
    finding_lines: list[str] = []
    for index, finding in enumerate(findings, start=1):
        if not isinstance(finding, dict):
            continue
        label = str(finding.get("risk_type") or finding.get("rule_id") or "核验项目")
        severity = str(finding.get("severity") or "未分级")
        reason = str(finding.get("reason") or "需人工核验")
        position = str(finding.get("clause_position") or "")
        finding_lines.append(f"{index}. {label}（{severity}）{position}：{reason}")
        citations.extend(str(item) for item in finding.get("citations", []) if item)
        for case in finding.get("case_evidence", []):
            if isinstance(case, dict):
                case_lines.append(
                    f"{case.get('case_id', '未标识案例')}：{case.get('title', '')} {case.get('summary', '')}".strip()
                )
        if finding.get("advice"):
            advice_lines.append(f"{index}. {finding['advice']}")

    citations.extend(str(item) for item in result.get("citations", []) if item)
    path = result.get("path") if isinstance(result.get("path"), list) else []
    if path:
        finding_lines.extend(
            f"{node.get('stage', '步骤')}：{node.get('action', '')}；材料：{node.get('materials', '')}"
            for node in path
            if isinstance(node, dict)
        )
    if result.get("content"):
        finding_lines.append("文书草稿：\n" + str(result["content"]))

    unique_citations = list(dict.fromkeys(citations))
    sections = [
        {
            "title": "处理摘要",
            "content": "已取得并校验证据"
            if result.get("evidence_status") == "verified"
            else "未取得可验证法条，以下项目均需人工核验。",
        },
        {"title": "风险与核验项目", "content": "\n".join(finding_lines) or "未识别到预设核验项。"},
        {"title": "法条依据", "content": "\n".join(unique_citations) or "本次未取得可验证法条。"},
        {"title": "参考案例", "content": "\n".join(case_lines) or "本次未检索到可追溯参考案例。"},
        {
            "title": "修改建议",
            "content": "\n".join(advice_lines) or "未生成建议；请结合完整事实人工核验。",
        },
        {"title": "使用提示", "content": str(result.get("disclaimer") or DISCLAIMER)},
    ]
    return {"title": title, "sections": sections}


def build_scenario_pdf(title: str, sections: list[dict[str, str]]) -> bytes:
    """生成无外部依赖、支持常见 PDF 阅读器的简要 CJK PDF。"""
    lines = [title, "LexRAG 法律场景报告"]
    for section in sections:
        lines.append(section.get("title", ""))
        lines.append(section.get("content", ""))
    lines.append(DISCLAIMER)
    content_lines = ["BT /F1 16 Tf 50 800 Td"]
    for index, line in enumerate(lines):
        encoded = str(line)[:70].encode("utf-16-be").hex().upper()
        if index:
            content_lines.append("0 -24 Td")
        content_lines.append(f"<{encoded}> Tj")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type0 /BaseFont /STSong-Light /Encoding /UniGB-UCS2-H /DescendantFonts [6 0 R] >>",
        b"<< /Type /Font /Subtype /CIDFontType0 /BaseFont /STSong-Light /CIDSystemInfo << /Registry (Adobe) /Ordering (GB1) /Supplement 2 >> >>",
    ]
    output = bytearray(b"%PDF-1.4\n% LexRAG\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode())
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    output.extend(b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:]))
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(output)
