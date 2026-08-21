"""Module 9: Exact OCR / Text Extraction Agent."""

import re
import uuid
from typing import Any

from pydantic import BaseModel, Field

from answer_eval.agents.ocr.schemas import OCRResult, OCRUncertainSpan
from answer_eval.core.errors import OCRExtractionError
from answer_eval.core.logging import get_logger
from answer_eval.core.provenance import Provenance
from answer_eval.inference.provider import InferenceProvider
from answer_eval.inference.types import ImageInput, InferenceRequest, ReasoningMode
from answer_eval.processing.segmentation.schemas import QuestionRegion
from answer_eval.prompts.manager import PromptManager

logger = get_logger("agents.ocr")


class _OCRStructuredPayload(BaseModel):
    """Internal Pydantic model for JSON output schema enforcement."""

    raw_text: str = Field(description="Exact verbatim transcription")
    lines: list[str] = Field(default_factory=list)
    uncertain_spans: list[dict[str, Any]] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)


def count_words_deterministic(text: str) -> int:
    """Calculate deterministic word count from raw text."""
    tokens = text.strip().split()
    return len(tokens)


class OCRAgent:
    """
    Extracts verbatim student handwriting from question region crops.
    Strictly forbids spelling correction, grammar fixing, or academic interpretation.
    """

    def __init__(
        self,
        inference_provider: InferenceProvider,
        prompt_manager: PromptManager | None = None,
    ) -> None:
        self.provider = inference_provider
        self.prompt_manager = prompt_manager or PromptManager()

    async def extract_text(
        self,
        region: QuestionRegion,
        task_name: str = "ocr",
    ) -> OCRResult:
        """Execute exact OCR extraction on a single QuestionRegion."""
        request_id = f"ocr-{uuid.uuid4().hex[:8]}"
        logger.info(
            "Executing OCR extraction",
            region_id=region.region_id,
            page_number=region.page_number,
            request_id=request_id,
        )

        if not region.crop_image_path:
            raise OCRExtractionError(
                f"Region '{region.region_id}' has no crop image path.",
                details={"region_id": region.region_id},
            )

        # Load prompt template
        prompt_text = self.prompt_manager.get_prompt_template(task_name)

        req = InferenceRequest(
            request_id=request_id,
            prompt=prompt_text,
            images=[ImageInput(image_path=region.crop_image_path, mime_type="image/png")],
            max_tokens=4096,
            temperature=0.0,
            reasoning_mode=ReasoningMode.DIRECT,
            metadata={
                "region_id": region.region_id,
                "submission_id": region.submission_id,
                "page_number": region.page_number,
            },
        )

        try:
            # Execute primary inference
            resp = await self.provider.infer(request=req)
            raw_text = resp.text.strip()

            # Check if output was empty and perform 1 controlled direct retry
            if not raw_text:
                logger.warning(
                    "OCR primary inference returned empty text — attempting controlled direct retry",
                    region_id=region.region_id,
                    request_id=request_id,
                )
                retry_req = req.model_copy(deep=True)
                retry_req.request_id = f"{request_id}-retry"
                retry_req.prompt = (
                    "Read the handwriting in this image.\n"
                    "Transcribe every visible handwritten word exactly as written.\n"
                    "Output ONLY the transcription.\n"
                    "Do not explain. Do not correct spelling. Do not invent missing text."
                )
                retry_req.max_tokens = 4096
                resp = await self.provider.infer(request=retry_req)
                raw_text = resp.text.strip()

            lines: list[str] = []
            uncertain_spans: list[OCRUncertainSpan] = []
            flags: list[str] = []

            # Check if output is JSON formatted (e.g. from structured provider or mock)
            if raw_text.startswith("{") and raw_text.endswith("}"):
                import json

                try:
                    data = json.loads(raw_text)
                    raw_text = data.get("raw_text", raw_text).strip()
                    lines = data.get("lines", [raw_text])
                    for u in data.get("uncertain_spans", []):
                        if isinstance(u, dict):
                            uncertain_spans.append(
                                OCRUncertainSpan(
                                    text=u.get("text", ""),
                                    reason=u.get("reason", "ambiguous"),
                                    position_hint=u.get("position_hint"),
                                )
                            )
                    flags = data.get("flags", [])
                except Exception:
                    pass

            if not lines and raw_text:
                lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

            # Extract illegible, crossed out, and inserted tags from text if not already populated
            if not uncertain_spans and raw_text:
                # 1. Illegible tags
                for m in re.finditer(r"\[ILLEGIBLE\]", raw_text, re.IGNORECASE):
                    uncertain_spans.append(
                        OCRUncertainSpan(
                            text="[ILLEGIBLE]",
                            reason="illegible",
                            position_hint=f"offset {m.start()}",
                        )
                    )
                # 2. Crossed out tags
                for m in re.finditer(r"\[CROSSED OUT:\s*([^\]]+)\]", raw_text, re.IGNORECASE):
                    uncertain_spans.append(
                        OCRUncertainSpan(
                            text=m.group(1),
                            reason="crossed_out",
                            position_hint=f"offset {m.start()}",
                        )
                    )
                # 3. Inserted tags
                for m in re.finditer(r"\[INSERTED:\s*([^\]]+)\]", raw_text, re.IGNORECASE):
                    uncertain_spans.append(
                        OCRUncertainSpan(
                            text=m.group(1),
                            reason="inserted_text",
                            position_hint=f"offset {m.start()}",
                        )
                    )

            word_count = count_words_deterministic(raw_text)
            status = "success" if raw_text else "empty_response"

            # Build Provenance
            provenance = Provenance(
                submission_id=region.submission_id,
                page_number=region.page_number,
                region_id=region.region_id,
                question_id=region.question_id,
                source_image_hash=region.crop_image_hash,
                source_image_path=region.crop_image_path,
                model_id=resp.model_id,
                quantization=resp.quantization,
                prompt_version="base_v1",
                request_id=request_id,
            )

            result = OCRResult(
                raw_text=raw_text,
                lines=lines,
                uncertain_spans=uncertain_spans,
                flags=flags,
                word_count=word_count,
                status=status,
                provenance=provenance,
                model_metadata={
                    "timing": resp.timing.model_dump(),
                    "usage": resp.usage.model_dump(),
                },
            )

            logger.info(
                "OCR extraction completed",
                region_id=region.region_id,
                status=status,
                word_count=word_count,
                uncertain_spans_count=len(uncertain_spans),
            )

            return result

        except Exception as e:
            raise OCRExtractionError(
                f"OCR agent failed on region {region.region_id}: {e}",
                details={"region_id": region.region_id, "request_id": request_id},
            ) from e
