from __future__ import annotations

import json

from scripts.run_stage8_answer_review import main, parse_args


def test_cli_accepts_a_positive_record_limit() -> None:
    assert parse_args(["--limit", "1"]).limit == 1


def test_cli_runs_one_sample_and_writes_a_credential_free_review_artifact(tmp_path) -> None:
    secret = "temporary-secret-must-not-appear"
    sample_path = tmp_path / "sample.jsonl"
    sample_path.write_text(
        json.dumps(
            {
                "id": "civil-001",
                "question": "成年人是指年满多少周岁？",
                "question_type": "baseline_direct_lookup",
                "difficulty": "baseline",
                "expected_knowledge_base_slugs": ["civil-code"],
                "relevant_article_ids": ["中华人民共和国民法典第17条"],
                "should_abstain": False,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    output_directory = tmp_path / "output"

    exit_code = main(
        [
            "--sample",
            str(sample_path),
            "--output-dir",
            str(output_directory),
            "--timestamp",
            "20261029T120000Z",
        ],
        environment={"STAGE8_LLM_API_KEY": secret, "STAGE8_AUTH_TOKEN": "signed-token"},
        request=lambda _payload, _headers, _timeout: {
            "answer": "十八周岁以上的自然人为成年人。",
            "citations": [],
            "verification_status": "pass",
            "verification_issues": [],
            "metadata": {"workflow_trace": []},
        },
    )

    assert exit_code == 0
    serialized = "\n".join(path.read_text(encoding="utf-8") for path in output_directory.iterdir())
    assert "civil-001" in serialized
    assert secret not in serialized
