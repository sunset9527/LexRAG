from app.services import langfuse_helper


def test_create_llm_allows_ninety_seconds_for_legal_evidence_generation(monkeypatch):
    captured: dict[str, object] = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(langfuse_helper, "ChatOpenAI", FakeChatOpenAI)

    langfuse_helper.create_llm(enable_langfuse=False)

    assert captured["request_timeout"] == 90
