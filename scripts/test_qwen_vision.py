"""Standalone verification script for Qwen3-VL through Ollama OpenAI-compatible API."""

import asyncio
import contextlib
import os
import sys
import time
from pathlib import Path

# Ensure project root is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))
if str(WORKSPACE_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT / "src"))

if sys.platform == "win32":
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8")

from PIL import Image, ImageDraw

from answer_eval.core.config import load_settings
from answer_eval.inference.ollama_provider import OllamaProvider
from answer_eval.services.vision import VisionService


def create_test_image(output_path: Path) -> Path:
    """Generate a clean test image with visual elements and text for testing."""
    img = Image.new("RGB", (600, 300), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Draw border and shapes
    draw.rectangle([20, 20, 580, 280], outline=(0, 0, 0), width=3)
    draw.rectangle([50, 60, 200, 160], outline=(0, 0, 180), fill=(230, 240, 255), width=2)
    draw.text((70, 100), "Client Node", fill=(0, 0, 120))

    draw.rectangle([380, 60, 530, 160], outline=(180, 0, 0), fill=(255, 235, 235), width=2)
    draw.text((400, 100), "Server Node", fill=(120, 0, 0))

    # Text for OCR testing with a deliberate spelling error
    draw.text((50, 200), "Machne lerning is a brnch of AI.", fill=(0, 0, 0))
    draw.text((50, 230), "Protocall use for comunication.", fill=(0, 0, 0))

    img.save(str(output_path), format="PNG")
    return output_path


async def main() -> None:
    settings = load_settings()
    base_url = os.getenv("OLLAMA_BASE_URL", settings.ollama.base_url)
    model_name = os.getenv("VISION_MODEL", settings.ollama.model)

    print("=" * 70)
    print(" [OLLAMA VISION] Qwen3-VL OpenAI-Compatible API Verification")
    print("=" * 70)
    print(f"Base URL   : {base_url}")
    print(f"Model Name : {model_name}")
    print(f"Timeout    : {settings.ollama.timeout_seconds}s")
    print("-" * 70)

    provider = OllamaProvider(base_url=base_url, model_name=model_name)
    service = VisionService(provider=provider)

    # 1. Health Check
    print("\n[Step 1/4] Checking Ollama Health & Model Availability...")
    health = await service.check_health()
    if not health.get("available"):
        print(f"[FAIL] Health check failed: {health.get('error')}")
        if health.get("help_message"):
            print(f"[HELP] Action: {health['help_message']}")
        sys.exit(1)

    print("[PASS] Ollama is online and healthy!")
    print(f"       Installed models: {health.get('installed_models', [])}")

    # 2. Test 1: Text-only Request
    print("\n[Step 2/4] Test 1: Text-only generation...")
    t0 = time.perf_counter()
    try:
        text_resp = await service.generate_text(prompt="Respond exactly with: QWEN_CONNECTION_OK")
        t_text = round((time.perf_counter() - t0) * 1000, 1)
        print(f'[PASS] Text response ({t_text}ms):\n       "{text_resp}"')
    except Exception as e:
        print(f"[FAIL] Text test failed: {e}")
        sys.exit(1)

    # Create temporary test image
    temp_img_dir = WORKSPACE_ROOT / "temp" / "test_verification"
    temp_img_dir.mkdir(parents=True, exist_ok=True)
    test_img_path = temp_img_dir / "sample_doc.png"
    create_test_image(test_img_path)

    # 3. Test 2: Image Understanding Request
    print("\n[Step 3/4] Test 2: Multimodal Image Understanding...")
    t0 = time.perf_counter()
    try:
        vis_resp = await service.analyze_image(
            image=test_img_path,
            prompt="Describe what you see in this image in 1-2 concise sentences.",
        )
        t_vis = round((time.perf_counter() - t0) * 1000, 1)
        print(f'[PASS] Vision response ({t_vis}ms):\n       "{vis_resp}"')
    except Exception as e:
        print(f"[FAIL] Vision test failed: {e}")
        sys.exit(1)

    # 4. Test 3: Strict OCR Transcription Request
    print("\n[Step 4/4] Test 3: Strict OCR Transcription Mode...")
    t0 = time.perf_counter()
    try:
        ocr_resp = await service.extract_ocr(image=test_img_path)
        t_ocr = round((time.perf_counter() - t0) * 1000, 1)
        print(f"[PASS] Exact OCR Output ({t_ocr}ms):")
        print("       " + "-" * 50)
        for line in ocr_resp.splitlines():
            print(f"       {line}")
        print("       " + "-" * 50)
    except Exception as e:
        print(f"[FAIL] OCR test failed: {e}")
        sys.exit(1)

    print("\n" + "=" * 70)
    print(" [SUCCESS] ALL TESTS PASSED SUCCESSFULLY! Qwen3-VL is fully operational.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
