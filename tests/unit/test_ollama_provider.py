"""Unit tests for OllamaProvider and VisionService."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from answer_eval.core.errors import (
    VisionRequestError,
)
from answer_eval.inference.ollama_provider import OllamaProvider, _encode_image_to_data_uri
from answer_eval.inference.types import ImageInput, InferenceRequest
from answer_eval.services.vision import VisionService


def test_ollama_provider_initialization() -> None:
    provider = OllamaProvider(
        base_url="http://127.0.0.1:11434/v1",
        model_name="qwen3-vl:4b",
        timeout_seconds=90.0,
        max_retries=3,
    )
    assert provider.base_url == "http://127.0.0.1:11434/v1"
    assert provider.model_name == "qwen3-vl:4b"
    assert provider.timeout_seconds == 90.0
    assert provider.max_retries == 3


def test_encode_image_to_data_uri(temp_workspace: Path, sample_image: Image.Image) -> None:
    img_path = temp_workspace / "sample.png"
    sample_image.save(img_path)

    img_input = ImageInput(image_path=str(img_path), mime_type="image/png")
    data_uri = _encode_image_to_data_uri(img_input)

    assert data_uri.startswith("data:image/png;base64,")
    assert len(data_uri) > 50

    # Nonexistent path
    with pytest.raises(VisionRequestError):
        _encode_image_to_data_uri(ImageInput(image_path="nonexistent.png"))


@pytest.mark.asyncio
async def test_ollama_detailed_health_check_online() -> None:
    provider = OllamaProvider(base_url="http://127.0.0.1:11434/v1", model_name="qwen3-vl:4b")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [{"id": "qwen3-vl:4b", "object": "model"}]}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        health = await provider.check_detailed_health()
        assert health["available"] is True
        assert "qwen3-vl:4b" in health["installed_models"]


@pytest.mark.asyncio
async def test_ollama_detailed_health_check_model_missing() -> None:
    provider = OllamaProvider(base_url="http://127.0.0.1:11434/v1", model_name="qwen3-vl:30b")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [{"id": "qwen3-vl:4b", "object": "model"}]}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        health = await provider.check_detailed_health()
        assert health["available"] is False
        assert "ollama pull qwen3-vl:30b" in health["help_message"]


@pytest.mark.asyncio
async def test_ollama_infer_success() -> None:
    provider = OllamaProvider(base_url="http://127.0.0.1:11434/v1", model_name="qwen3-vl:4b")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "QWEN_CONNECTION_OK"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        req = InferenceRequest(request_id="req-1", prompt="Hello")
        resp = await provider.infer(req)
        assert resp.text == "QWEN_CONNECTION_OK"
        assert resp.usage.total_tokens == 15
        assert resp.provider == "ollama"


@pytest.mark.asyncio
async def test_vision_service_methods(temp_workspace: Path, sample_image: Image.Image) -> None:
    img_path = temp_workspace / "doc.png"
    sample_image.save(img_path)

    provider = OllamaProvider(base_url="http://127.0.0.1:11434/v1", model_name="qwen3-vl:4b")
    service = VisionService(provider=provider)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "The protocall is use for comunication"}}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        # Text
        txt = await service.generate_text("Hi")
        assert "protocall" in txt

        # Image analysis
        vis = await service.analyze_image(image=img_path, prompt="Describe")
        assert "protocall" in vis

        # OCR
        ocr = await service.extract_ocr(image=img_path)
        assert "protocall" in ocr
