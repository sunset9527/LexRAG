# -*- coding: utf-8 -*-
import io, json, os, itertools, collections
D = r"E:\个人发展\002职业\Legal_RAG_Agent-stage8-freeze\reports\evaluation\stage8\answer_reviews"
A = os.path.join(D, "stage8_answer_review_merged_100.jsonl")
B = os.path.join(D, "stage8_answer_review_merged_100_reviewed.jsonl")
a = [json.loads(l) for l in io.open(A, encoding="utf-8") if l.strip()]
b = [json.loads(l) for l in io.open(B, encoding="utf-8") if l.strip()]
print("rows:", len(a), len(b), "| id唯一:", len({r["id"] for r in b}) == 100)
MUTABLE = {"human_review", "review_note", "review_state", "reviewer", "reviewed_at"}
changed = collections.Counter()
bad = 0
for x, y in zip(a, b):
    assert set(x.keys()) == set(y.keys())
    for k in x:
        if k in MUTABLE: continue
        if x[k] != y[k]:
            bad += 1
            print("FROZEN FIELD CHANGED:", x["id"], k)
    for k in MUTABLE:
        if x[k] != y[k]: changed[k] += 1
print("冻结字段被改动:", bad)
print("变更字段计数:", dict(changed))
print("review_state:", dict(collections.Counter([r["review_state"] for r in b])))
print("human_review:", dict(collections.Counter([r["human_review"] for r in b])))
print("reviewer:", {r["reviewer"] for r in b}, "| reviewed_at:", {r["reviewed_at"] for r in b})
print("空 note:", sum(1 for r in b if not r["review_note"].strip()))
print("\n=== rejected 3 条 ===")
for r in b:
    if r["review_state"] == "rejected":
        print(f'[{r["id"]}] human_review={r["human_review"]}')
        print("  note:", r["review_note"])
print("\n=== 抽样 approved ===")
for rid in ("civil-002","company-006","hard-abstain-004","round2-oral-039"):
    for r in b:
        if r["id"] == rid:
            print(f'[{rid}] {r["review_state"]} note:', r["review_note"])
