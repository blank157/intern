"""Live integrated OCR verification: OllamaProvider + OCRAgent with new config.

Runs the actual project inference stack (native /api/chat with think=false,
temperature=0, num_predict=4096, strict prompt) over test crops and prints
per-segment [OCR]-style results. Run from project root:
  python scripts/test_ocr_live_pipeline.py
"""

import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from answer_eval.agents.ocr.agent import OCRAgent  # noqa: E402
from answer_eval.inference.ollama_provider import OllamaProvider  # noqa: E402
from answer_eval.processing.segmentation.schemas import BoundingBox, QuestionRegion  # noqa: E402

CROPS = [
    ("small_test_01", ROOT / "temp/test_5regions/region_01.png"),
    ("large_test_01", ROOT / "temp/test_e2e_verification/crops/SUB-LIVE-TEST_p01_r01_9d3dcc22.png"),
]


def make_region(name: str, crop: Path) -> QuestionRegion:
    return QuestionRegion(
        region_id=name,
        page_number=1,
        submission_id="SUB-LIVE-VERIFY",
        question_id="Q1",
        bbox=BoundingBox(x_min=0.0, y_min=0.0, x_max=1.0, y_max=1.0),
        crop_image_path=str(crop),
        crop_image_hash=f"hash-{name}",
    )


async def main() -> None:
    # Model / num_ctx / num_predict / temperature come from centralized OCR config
    provider = OllamaProvider(timeout_seconds=600.0)
    health = await provider.check_detailed_health()
    print(f"Health: available={health['available']} model={health['model']}")
    if not health["available"]:
        print(health.get("help_message"))
        return

    agent = OCRAgent(inference_provider=provider)
    for name, crop in CROPS:
        loop = asyncio.get_event_loop()
        t0 = loop.time()
        result = await agent.extract_text(make_region(name, crop))
        wall = round(loop.time() - t0, 2)
        meta = result.model_metadata
        print("=" * 70)
        print(
            f"[OCR] segment: {name}\n"
            f"       model: {result.provenance.model_id}\n"
            f"       thinking_disabled: {meta.get('thinking_disabled')}\n"
            f"       stop_reason: {meta.get('stop_reason')}\n"
            f"       attempts: {meta.get('attempts')}\n"
            f"       provider_time: {meta['timing'].get('total_inference_ms', 0) / 1000:.2f}s"
            f"   wall_time: {wall}s\n"
            f"       characters: {len(result.raw_text)}   words: {result.word_count}\n"
            f"       status: {result.status}   flags: {result.flags}"
        )
        preview = result.raw_text[:500]
        print(f"------- transcription preview -------\n{preview}")

    await provider.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
