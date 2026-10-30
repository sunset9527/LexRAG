from __future__ import annotations

import json

import pytest

from src.evaluation.stage8_answer_review_runner import (
    AnswerReviewRunConfig,
    AnswerReviewRunnerError,
    build_runtime_headers,
    run_answer_review_records,
    write_answer_review_artifacts,
)


def _record() -> dict:
    return {
        "id": "civil-001",
        "question": "成年人是指年满多少周岁？",
        "expected_knowledge_base_slugs": ["civil-code"],
        "should_abstain": False,
    }


def test_runtime_headers_require_authentication_without_disclosing_the_llm_key() -> None:
    secret = "temporary-secret-must-not-appear"

    with pytest.raises(AnswerReviewRunnerError) as raised:
        build_runtime_headers({"STAGE8_LLM_API_KEY": secret})

    assert "STAGE8_AUTH_TOKEN" in str(raised.value)
    assert secret not in str(raised.value)


def test_runner_records_a_real_query_response_without_putting_credentials_in_result() -> None:
    observed: dict = {}

    def request(payload: dict, headers: dict[str, str], _timeout: float) -> dict:
        observed["payload"] = payload
        observed["headers"] = headers
        return {
            "answer": "十八周岁以上的自然人为成年人。",
            "citations": [{"citation_text": "【中华人民共和国民法典第17条】"}],
            "verification_status": "pass",
            "verification_issues": [],
            "metadata": {"workflow_trace": [{"node": "answer", "status": "completed"}]},
        }

    secret = "temporary-secret-must-not-appear"
    headers = build_runtime_headers(
        {"STAGE8_LLM_API_KEY": secret, "STAGE8_AUTH_TOKEN": "signed-token"}
    )
    result = run_answer_review_records(
        [_record()], request, headers=headers, config=AnswerReviewRunConfig(max_attempts=1)
    )

    assert observed["payload"] == {
        "query": "成年人是指年满多少周岁？",
        "knowledge_base_ids": ["civil-code"],
        "config": {"cache_bypass": True},
    }
    assert observed["headers"]["Authorization"] == "Bearer signed-token"
    assert observed["headers"]["X-API-Key"] == secret
    assert result[0]["sample_id"] == "civil-001"
    assert result[0]["status"] == "completed"
    assert result[0]["answer"] == "十八周岁以上的自然人为成年人。"
    assert result[0]["workflow_trace"] == [{"node": "answer", "status": "completed"}]
    assert result[0]["latency_ms"] >= 0
    assert secret not in json.dumps(result, ensure_ascii=False)


def test_runner_keeps_a_timeout_as_an_explicit_failed_record_after_one_retry() -> None:
    calls = 0

    def request(_payload: dict, _headers: dict[str, str], _timeout: float) -> dict:
        nonlocal calls
        calls += 1
        raise TimeoutError("provider request timed out")

    result = run_answer_review_records(
        [_record()],
        request,
        headers={"Authorization": "Bearer signed-token", "X-API-Key": "hidden"},
        config=AnswerReviewRunConfig(max_attempts=2),
    )

    assert calls == 2
    assert result[0]["sample_id"] == "civil-001"
    assert result[0]["status"] == "execution_error"
    assert result[0]["attempts"] == 2
    assert result[0]["error_type"] == "TimeoutError"
    assert result[0]["latency_ms"] >= 0


def test_runner_records_a_safe_transport_error_code_without_response_content() -> None:
    class SafeRequestError(RuntimeError):
        error_code = "HTTP_401"

    def request(_payload: dict, _headers: dict[str, str], _timeout: float) -> dict:
        raise SafeRequestError()

    result = run_answer_review_records(
        [_record()],
        request,
        headers={"Authorization": "Bearer signed-token", "X-API-Key": "hidden"},
        config=AnswerReviewRunConfig(max_attempts=1),
    )

    assert result[0]["error_type"] == "HTTP_401"


def test_runner_does_not_retry_a_non_transient_http_client_error() -> None:
    calls = 0

    class SafeRequestError(RuntimeError):
        error_code = "HTTP_400"

    def request(_payload: dict, _headers: dict[str, str], _timeout: float) -> dict:
        nonlocal calls
        calls += 1
        raise SafeRequestError()

    result = run_answer_review_records(
        [_record()],
        request,
        headers={"Authorization": "Bearer signed-token", "X-API-Key": "hidden"},
        config=AnswerReviewRunConfig(max_attempts=2),
    )

    assert calls == 1
    assert result[0]["attempts"] == 1
    assert result[0]["error_type"] == "HTTP_400"


def test_runner_throttles_between_records_to_respect_the_query_rate_limit() -> None:
    records = [_record(), {**_record(), "id": "civil-002"}]
    sleeps: list[float] = []

    result = run_answer_review_records(
        records,
        lambda _payload, _headers, _timeout: {
            "answer": "ok",
            "citations": [],
            "verification_status": "pass",
            "verification_issues": [],
            "metadata": {"workflow_trace": []},
        },
        headers={"Authorization": "Bearer signed-token", "X-API-Key": "hidden"},
        config=AnswerReviewRunConfig(max_attempts=1, minimum_interval_seconds=1.1),
        sleep=sleeps.append,
    )

    assert [item["status"] for item in result] == ["completed", "completed"]
    assert sleeps == [1.1]


def test_writer_binds_review_output_to_input_sample_without_writing_credentials(tmp_path) -> None:
    secret = "temporary-secret-must-not-appear"
    artifacts = write_answer_review_artifacts(
        output_directory=tmp_path,
        sample_records=[_record()],
        results=[
            {
                "sample_id": "civil-001",
                "status": "completed",
                "attempts": 1,
                "answer": "十八周岁以上的自然人为成年人。",
                "citations": [],
                "verification_status": "pass",
                "verification_issues": [],
                "workflow_trace": [],
            }
        ],
        run_metadata={"api_base_url": "http://127.0.0.1:8000", "secret": secret},
        timestamp="20261029T120000Z",
    )

    line = json.loads(artifacts.result_path.read_text(encoding="utf-8").strip())
    manifest = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))

    assert line["sample_id"] == "civil-001"
    assert line["question_type"] == ""
    assert line["expected_knowledge_base_slugs"] == ["civil-code"]
    assert manifest["counts"] == {"completed": 1, "execution_error": 0, "total": 1}
    assert manifest["result"]["sha256"]
    serialized = artifacts.result_path.read_text(encoding="utf-8") + artifacts.manifest_path.read_text(
        encoding="utf-8"
    )
    assert secret not in serialized
