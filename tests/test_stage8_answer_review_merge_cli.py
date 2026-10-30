from __future__ import annotations

import json

from scripts.merge_stage8_answer_review import main


def _sample(identifier: str) -> dict:
    return {
        "id": identifier,
        "question": f"{identifier} 的问题",
        "review_state": "pending",
        "reviewer": "",
        "reviewed_at": "",
        "review_note": "",
        "human_review": None,
    }


def _run(identifier: str) -> dict:
    return {
        "sample_id": identifier,
        "status": "completed",
        "answer": "答复",
        "citations": [],
        "verification_status": "pass",
        "verification_issues": [],
        "workflow_trace": [],
        "attempts": 1,
        "latency_ms": 1.0,
    }


def _write_jsonl(path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def test_cli_writes_hash_bound_merged_pending_review_artifact(tmp_path) -> None:
    sample = tmp_path / "sample.jsonl"
    initial = tmp_path / "initial.jsonl"
    resume = tmp_path / "resume.jsonl"
    output = tmp_path / "merged.jsonl"
    _write_jsonl(sample, [_sample("civil-001"), _sample("civil-002")])
    _write_jsonl(initial, [_run("civil-001")])
    _write_jsonl(resume, [_run("civil-002")])

    assert main(["--sample", str(sample), "--initial-run", str(initial), "--resume-run", str(resume), "--output", str(output)]) == 0

    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    manifest = json.loads(output.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    assert [row["id"] for row in rows] == ["civil-001", "civil-002"]
    assert manifest["counts"] == {"completed": 2, "total": 2}
    assert manifest["result"]["sha256"]
    assert manifest["source"]["sample"]["sha256"]
