"""AnswerKeyParserAgent — turns the converted source document into
`answer-key-v1` structured JSON using the configured VLM provider.

Contract (per architecture §12): extract what the teacher supplied WITHOUT
inventing rubric information. Missing marks/concepts stay empty; doubts are
reported as warnings so the teacher review step resolves them.
"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from answer_eval.answerkey.converters import SourceDocument
from answer_eval.answerkey.schemas import ANSWER_KEY_SCHEMA_VERSION, ParsedAnswerKey
from answer_eval.inference.provider import InferenceProvider
from answer_eval.inference.types import ImageInput, InferenceRequest, ReasoningMode

logger = logging.getLogger(__name__)

PARSER_PROMPT_VERSION = "answer-key-parser-v1"

SYSTEM_PROMPT = """You convert teacher answer keys into structured JSON.
Rules:
- Extract ONLY what is present in the document. Never invent marks, concepts, keywords or diagrams.
- question_count MUST equal the number of real questions you extracted.
- If a mark value is missing, use 0 for maximum_marks and add a parser warning.
- Split expected answers into expected_concepts only when the key clearly allocates separate points;
  otherwise leave expected_concepts empty.
- keywords are important technical terms from the expected answer; mandatory_terms only when the key
  explicitly demands them.
- For numerical/math questions allocate math_rubric steps ONLY if the key shows step-wise marking.
- diagram_hints: when a question's answer includes a figure/diagram in this document, report its page
  number and, if you can locate it, a normalized bbox [x_min,y_min,x_max,y_max] on that page.
- Respond with JSON matching the provided schema exactly."""

USER_TEMPLATE = """Convert this answer key into {schema_name} JSON.

Document text:
---
{document_text}
---

Return only the JSON object."""


class AnswerKeyParserAgent:
    def __init__(
        self,
        provider: InferenceProvider,
        *,
        prompt_version: str = PARSER_PROMPT_VERSION,
        max_tokens: int = 8192,
    ) -> None:
        self._provider = provider
        self._prompt_version = prompt_version
        self._max_tokens = max_tokens
        self.last_model_id: str | None = None

    @property
    def prompt_version(self) -> str:
        return self._prompt_version

    async def parse(self, document: SourceDocument) -> ParsedAnswerKey:
        images = [
            ImageInput(image_bytes=page.image_bytes, mime_type="image/png")
            for page in document.pages
            if page.image_bytes
        ]
        prompt = USER_TEMPLATE.format(
            schema_name="answer-key-v1",
            document_text=document.full_text(),
        )
        request = InferenceRequest(
            request_id=f"answer-key-parse-{abs(hash(prompt)) % 10_000_000}",
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT,
            images=images,
            max_tokens=self._max_tokens,
            temperature=0.0,
            reasoning_mode=ReasoningMode.DIRECT,
        )
        # `infer_structured` is async on every InferenceProvider — it MUST be
        # awaited, otherwise we get a coroutine object instead of a response
        # and crash with AttributeError on `.model_id`.
        response = await self._provider.infer_structured(request, ParsedAnswerKey.model_json_schema())
        self.last_model_id = response.model_id
        payload = response.structured_data if response.structured_data else self._extract_json(response.text or "")
        try:
            parsed = ParsedAnswerKey.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(f"Parser output failed schema validation: {exc}") from exc
        parsed.schema_version = ANSWER_KEY_SCHEMA_VERSION
        return parsed.validated()

    @staticmethod
    def _extract_json(text: str) -> dict:
        import json

        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("Parser returned no JSON object")
        return json.loads(cleaned[start : end + 1])


class FakeAnswerKeyParserAgent:
    """Deterministic stand-in for tests/plumbing without a live VLM."""

    def __init__(self, result: ParsedAnswerKey | None = None) -> None:
        self.result = result or _default_fixture()
        self.calls = 0
        self.last_model_id = "fake-parser"
        self.prompt_version = "fake-v1"

    async def parse(self, document: SourceDocument) -> ParsedAnswerKey:
        self.calls += 1
        return self.result


def _default_fixture() -> ParsedAnswerKey:
    from answer_eval.answerkey.schemas import ParsedConcept, ParsedDiagramHint, ParsedQuestion

    return ParsedAnswerKey(
        title="Fixture key",
        question_count=2,
        questions=[
            ParsedQuestion(
                question_number=1,
                question_text="Explain flow control.",
                maximum_marks=4,
                answer_type="explain",
                expected_answer_text="Receiver regulates sender via acknowledgements and windowing.",
                expected_concepts=[ParsedConcept(concept_code="C1", description="Acknowledgements", maximum_marks=2)],
                keywords=["acknowledgement", "window"],
                mandatory_terms=["acknowledgement"],
            ),
            ParsedQuestion(
                question_number=2,
                question_text="Draw the three-way handshake.",
                maximum_marks=6,
                answer_type="diagram",
                expected_answer_text="SYN, SYN-ACK, ACK exchange between client and server.",
                diagram_hints=[ParsedDiagramHint(page=1, ordinal=1, type_label="TCP handshake", uncertain=True)],
                parser_uncertainties=["diagram location uncertain"],
            ),
        ],
        parser_warnings=["Fixture data — replace with a real model run"],
    )
