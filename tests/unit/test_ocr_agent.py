"""Unit tests for Module 9: OCR Agent (Exact Verbatim Transcription)."""

from pathlib import Path

import pytest

from answer_eval.agents.ocr.agent import OCRAgent, count_words_deterministic
from answer_eval.agents.ocr.schemas import OCRResult
from answer_eval.processing.segmentation.schemas import BoundingBox, QuestionRegion
from tests.conftest import MockInferenceProvider


def test_deterministic_word_count() -> None:
    text = "The protocall is use for comunication between network layers."
    assert count_words_deterministic(text) == 9
    assert count_words_deterministic("   ") == 0
    assert count_words_deterministic("one\ntwo\tthree") == 3


@pytest.mark.asyncio
async def test_ocr_agent_extraction(mock_provider: MockInferenceProvider, temp_workspace: Path) -> None:
    # Create fake crop image file
    crop_file = temp_workspace / "crop1.png"
    crop_file.write_bytes(b"\x89PNG\r\n\x1a\nfake_image_bytes")

    region = QuestionRegion(
        region_id="REG-P01-01",
        page_number=1,
        submission_id="SUB-01",
        question_id="Q1",
        bbox=BoundingBox(x_min=0.0, y_min=0.0, x_max=1.0, y_max=0.5),
        crop_image_path=str(crop_file),
        crop_image_hash="abc_crop_hash",
    )

    ocr_agent = OCRAgent(inference_provider=mock_provider)
    result = await ocr_agent.extract_text(region)

    assert isinstance(result, OCRResult)
    # Check verbatim spelling mistake preservation
    assert "protocall" in result.raw_text
    assert "comunication" in result.raw_text
    assert result.word_count == 6
    assert result.provenance.region_id == "REG-P01-01"
    assert result.provenance.submission_id == "SUB-01"
    assert result.provenance.source_image_hash == "abc_crop_hash"
    assert result.provenance.model_id == "qwen_vl_4b_q8"
