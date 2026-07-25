"""chat_json retries transient OpenAI server errors."""

from types import SimpleNamespace

import pytest

from app.agents.visual_summary import llm_json


class _FakeAPIStatusError(Exception):
    def __init__(self, status_code: int, message: str = "server error"):
        super().__init__(message)
        self.status_code = status_code


def test_chat_json_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    class Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    calls["n"] += 1
                    if calls["n"] < 3:
                        raise _FakeAPIStatusError(
                            500,
                            "The server had an error processing your request",
                        )
                    return SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))]
                    )

    # Treat our fake as retryable via message matching.
    monkeypatch.setattr(
        llm_json,
        "_TRANSIENT_OPENAI",
        (Exception,),
    )
    sleeps: list[float] = []
    monkeypatch.setattr(llm_json.time, "sleep", lambda s: sleeps.append(s))

    resp = llm_json.chat_json(
        Client(),
        model="gpt-test",
        system="s",
        prompt="p",
        schema_name="test",
        schema={"type": "object", "properties": {}, "additionalProperties": False},
        max_retries=3,
    )
    assert resp.choices[0].message.content == "{}"
    assert calls["n"] == 3
    assert len(sleeps) == 2


def test_is_retryable_detects_openai_server_error_text():
    err = Exception(
        "Error code: 500 - {'error': {'message': 'The server had an error "
        "processing your request.', 'type': 'server_error'}}"
    )
    assert llm_json._is_retryable_openai_error(err) is True
