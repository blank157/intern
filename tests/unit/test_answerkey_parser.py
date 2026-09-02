"""Regression tests for AnswerKeyParserAgent (live-parser async contract).

Root cause of the production "Parser crashed; see server logs" bug:
`infer_structured` is `async` on every real InferenceProvider, but the parser
used to call it without `await`, yielding a coroutine object that crashed with
AttributeError on `.model_id`. These tests drive the REAL agent against an
async scripted provider — the exact path no earlier test covered.
"""

from __future__ import annotations

import asyncio

from answer_eval.answerkey.converters import convert_source
from answer_eval.answerkey.parser import AnswerKeyParserAgent, _default_fixture
from answer_eval.answerkey.schemas import ANSWER_KEY_SCHEMA_VERSION, ParsedAnswerKey
from answer_eval.inference.types import InferenceResponse


class AsyncScriptedProvider:
    """Mimics OllamaProvider's async surface: async initialize + infer_structured."""

    def __init__(self, data: dict) -> None:
        self.data = data
        self.initialize_calls = 0
        self.parse_calls = 0

    async def initialize(self, model, config, hardware=None) -> None:
        self.initialize_calls += 1

    async def infer_structured(self, request, schema, max_retries: int = 2):
        self.parse_calls += 1
        return InferenceResponse(
            request_id=request.request_id,
            provider="fake-async",
            model_id="fake-4b",
            text="structured",
            structured_data=self.data,
        )


def _pdf_bytes(text: str) -> bytes:
    import fitz

    doc = fitz.open()
    doc.new_page().insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def test_parse_awaits_async_provider_and_returns_validated_key() -> None:
    payload = _default_fixture().model_dump(mode="json")
    provider = AsyncScriptedProvider(payload)
    agent = AnswerKeyParserAgent(provider)
    document = convert_source("key.pdf", _pdf_bytes("Q1. Define TCP.\nAnswer: protocol"))

    parsed = asyncio.run(agent.parse(document))

    assert provider.parse_calls == 1
    assert isinstance(parsed, ParsedAnswerKey)
    # .model_id access proves we got a real InferenceResponse, not a coroutine.
    assert agent.last_model_id == "fake-4b"
    assert parsed.schema_version == ANSWER_KEY_SCHEMA_VERSION
    assert parsed.question_count == len(parsed.questions)


def test_parse_wraps_schema_validation_failure_in_value_error() -> None:
    provider = AsyncScriptedProvider({"unexpected": True})  # missing required `questions`
    agent = AnswerKeyParserAgent(provider)
    document = convert_source("key.pdf", _pdf_bytes("fixture"))

    try:
        asyncio.run(agent.parse(document))
    except ValueError as exc:
        assert "schema validation" in str(exc)
    else:
        raise AssertionError("expected ValueError for invalid parser payload")

