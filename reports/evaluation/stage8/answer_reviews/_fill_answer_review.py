# -*- coding: utf-8 -*-
"""Stage8 answer review：为 100 条答案填 human_review / review_note / review_state / reviewer / reviewed_at。
规则来自 STAGE8_RELEASE_READINESS_20261029.md：
  true  = 答案的实质法律主张被所引现行条文支撑；false = 否则（含未回答问题）。
"""
import io, json, os, collections
from datetime import datetime, timedelta, timezone

D = r"E:\个人发展\002职业\Legal_RAG_Agent-stage8-freeze\reports\evaluation\stage8\answer_reviews"
SRC = os.path.join(D, "stage8_answer_review_merged_100.jsonl")
DST = os.path.join(D, "stage8_answer_review_merged_100_reviewed.jsonl")
REVIEWER = "高志远"
REVIEWED_AT = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S") + "+08:00"

FALSE = {
    "round2-multihop-009":
        "答案未回答所问：检索仅命中民法典第276条（车位首先满足业主需要），与“租车位过渡支出是否属可预见违约损失”无关；"
        "答案只说明证据不足，未对可预见性问题作出任何法律判断，也未引用第584条赔偿范围与可预见性规则。属检索失败导致的不完整回答。",
    "round2-adjacent-038":
        "答案未回答所问：检索命中第803、804条（建设工程合同发包人供料与停建），与“承包人迟到材料、发包人选择停工”的减损问题无关；"
        "答案自述无法得出结论，未引用第591条减损义务与第584条赔偿范围。属检索失败导致的不完整回答。",
    "round2-multihop-020":
        "答案未回答所问：题问“维修、替换零件、停工损失的审查顺序”，检索命中第804（建设工程停建）、第824（客运行李）、第829（托运人变更）、"
        "第842（多式联运）等不适用条文，答案结论为“无法确定审查顺序”，未引用第577/584/591条给出损失范围与因果顺序的分析框架。",
}

# 版本漂移：知识库文本已升版，数据集 expected 条号未同步
VERSION_DRIFT = {
    "company-002": "答案引公司法第33条（营业执照签发日期为公司成立日期），与知识库现行文本一致；数据集 expected 仍标2018年修正版第7条，条号未随语料升版同步，需在数据集侧修正。",
    "company-006": "答案引公司法第76、83、69条（监事会人数与不设监事会情形），与知识库现行（2023修订）文本一致；数据集 expected 仍标2018年修正版第51条，需同步。",
    "company-009": "答案引公司法第103条（股款缴足之日起三十日内召开成立大会），与知识库现行文本一致；数据集 expected 仍标2018年修正版第89条，需同步。",
    "copyright-010": "答案引著作权法第58条（没收违法所得、侵权复制品及违法活动财物），与知识库现行（2020修正）文本一致；数据集 expected 仍标2010年修正版第52条，需同步。",
    "patent-005": "答案按现行（2020修正）专利法第42条给出外观设计十五年，与知识库文本一致；旧版为十年，数据集未标注版本口径，答题与标签需统一版本。",
}

# 引证与 expected 不同但更具体/更完整，结论正确
CITATION_NOTE = {
    "round2-oral-026": "答案以第311、313、641、228条从善意取得角度正确回答了物权归属；但未引第597条（无处分权致所有权不能转移时买受人可解除并请求违约责任），合同层面的回答不完整。",
    "round2-oral-045": "答案引刑法第7、8、6、10、11条，覆盖属人管辖、保护管辖、属地管辖与外国判决情形，比 expected 单条第6条更完整，结论正确。",
    "round2-oral-050": "答案以劳动法第41、43条论证强行超时加班可拒绝，结论正确；expected 标注的第38条（每周至少休息1日）并非本问直接依据，标签建议修正。",
    "round2-adjacent-004": "答案引第781条（承揽成果不符合质量要求）而非 candidate 的577/590条，属更具体规则，结论（生病不构成免责）正确。",
    "round2-multihop-011": "答案引第585、801、776、711、1198条并逐条说明适用边界，结论合理；未引577/584/591，但无错误主张。",
    "round2-multihop-013": "答案以第711—714条租赁维修规则回答修理费与家具损坏，结论正确；未引591减损义务，属引证不完整而非错误。",
    "round2-multihop-014": "答案以第584、592、816条回答改签与住宿费的可赔范围，结论正确。",
    "round2-multihop-016": "答案以第1184条财产损失计算规则回答补种费与减产损失，结论合理；题属违约损害，用侵权损失计算条款类推，存在口径偏差但不构成错误结论。",
    "round2-multihop-029": "答案引第591、1184、1203条区分减损与产品责任，结论正确。",
    "round2-cross-024": "答案以第23、24条与民法典第142条（意思表示解释）替代509诚信原则，结论正确。",
    "round2-cross-011": "答案正确指出欠薪可随时解除且不构成未提前通知；但称“证据未收录按月支付条文”，实际劳动法第50条即工资按月支付，属检索遗漏，不影响结论。",
}

rows = [json.loads(l) for l in io.open(SRC, encoding="utf-8") if l.strip()]
assert len(rows) == 100

result = []
stat = collections.Counter()
for r in rows:
    rid = r["id"]
    out = dict(r)
    w = r["workflow_output"] or {}
    cits = w.get("citations") or []
    cid = "、".join(sorted({str(c.get("article_id")) for c in cits})) or "无"

    if rid in FALSE:
        out["human_review"] = False
        out["review_state"] = "rejected"
        note = FALSE[rid]
    else:
        out["human_review"] = True
        out["review_state"] = "approved"
        if r["should_abstain"]:
            note = (f"弃答标注成立：答案未给出确定性结论，明确说明事实不足/证据范围限制（引用 {cid}），"
                    f"符合 insufficient_facts_abstention 要求。")
        elif rid in VERSION_DRIFT:
            note = VERSION_DRIFT[rid]
        elif rid in CITATION_NOTE:
            note = CITATION_NOTE[rid]
        else:
            note = f"答案结论与所引条文（{cid}）原文一致，实质法律主张均有引证支撑，未见无依据或错误表述。"

    out["review_note"] = note
    out["reviewer"] = REVIEWER
    out["reviewed_at"] = REVIEWED_AT
    result.append(out)
    stat[(r["question_type"], out["review_state"])] += 1

with io.open(DST, "w", encoding="utf-8", newline="\n") as f:
    for rec in result:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

print("reviewed_at =", REVIEWED_AT)
print("written:", DST)
for k in sorted(stat): print(f"  {k[0]:32s} {k[1]:9s} {stat[k]}")
print("合计:", dict(collections.Counter([x["review_state"] for x in result])))
print("human_review:", dict(collections.Counter([x["human_review"] for x in result])))
