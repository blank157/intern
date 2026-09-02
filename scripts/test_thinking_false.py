"""OCR before/after comparison harness.

Runs the exact same crop through:
  BEFORE: old inference path — OpenAI-compatible /v1/chat/completions, no think control
  AFTER:  new inference path — native /api/chat with think=false, num_ctx=16384

Uses actual measurements only. Run from project root:
  python scripts/test_ocr_before_after.py
"""

import base64
import sys
import time
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
MODEL = "qwen3-vl:4b"
BASE = "http://localhost:11434"
PROMPT = (ROOT / "src/answer_eval/prompts/templates/ocr/base.txt").read_text(encoding="utf-8")

CROPS = {
    "small_test_01": ROOT / "temp/test_5regions/region_01.png",
    "large_test_01": ROOT / "temp/test_e2e_verification/crops/SUB-LIVE-TEST_p01_r01_9d3dcc22.png",
}


def run_before(crop: Path, num_predict: int) -> dict:
    """Old path: OpenAI-compatible /v1/chat/completions without any thinking control."""
    b64 = base64.b64encode(crop.read_bytes()).decode()
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
        "max_tokens": num_predict,
        "temperature": 0.0,
        "stream": False,
    }
    t0 = time.perf_counter()
    r = httpx.post(f"{BASE}/v1/chat/completions", json=payload, timeout=600)
    dt = time.perf_counter() - t0
    d = r.json()
    ch = (d.get("choices") or [{}])[0]
    content = ((ch.get("message") or {}).get("content") or "").strip()
    return {
        "mode": "BEFORE",
        "duration_s": round(dt, 2),
        "finish_reason": ch.get("finish_reason"),
        "completion_tokens": (d.get("usage") or {}).get("completion_tokens"),
        "content_chars": len(content),
        "content": content,
    }


def run_after(crop: Path, num_predict: int) -> dict:
    """New path: native /api/chat with think=False + closed-<think> assistant prefill."""
    b64 = base64.b64encode(crop.read_bytes()).decode()
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": PROMPT, "images": [b64]},
            {"role": "assistant", "content": "<think>\n\n</think>\n\n"},
        ],
        "think": False,
        "stream": False,
        "options": {"num_ctx": 16384, "num_predict": num_predict, "temperature": 0},
    }
    t0 = time.perf_counter()
    r = httpx.post(f"{BASE}/api/chat", json=payload, timeout=600)
    dt = time.perf_counter() - t0
    d = r.json()
    msg = d.get("message") or {}
    content = (msg.get("content") or "").strip()
    thinking = msg.get("thinking") or ""
    return {
        "mode": "AFTER",
        "duration_s": round(dt, 2),
        "finish_reason": d.get("done_reason"),
        "completion_tokens": d.get("eval_count"),
        "content_chars": len(content),
        "thinking_chars": len(thinking),
        "content": content,
    }


def report(name: str, res: dict) -> None:
    status = (
        "SUCCESS"
        if res["content_chars"] > 0 and res["finish_reason"] not in ("length",)
        else ("TRUNCATED" if res["content_chars"] > 0 else "FAIL(empty)")
    )
    print(f"\n{'=' * 70}")
    print(f"Crop: {name}   Mode: {res['mode']}   Model: {MODEL}")
    print(f"Time: {res['duration_s']}s   Finish/Stop reason: {res['finish_reason']}"
          f"   Completion tokens: {res['completion_tokens']}")
    print(f"Output: {res['content_chars']} characters   Status: {status}")
    if res.get("thinking_chars"):
        print(f"(internal thinking text returned separately: {res['thinking_chars']} chars)")
    preview = res["content"][:400]
    print(f"Preview: {preview!r}")


def main() -> None:
    num_predict = int(sys.argv[1]) if len(sys.argv) > 1 else 4096
    only = sys.argv[2] if len(sys.argv) > 2 else None
    for name, crop in CROPS.items():
        if only and only not in name:
            continue
        print(f"\n########## {name} ({crop.name}, {crop.stat().st_size // 1024} KB) "
              f"num_predict={num_predict} ##########")
        report(name, {**run_before(crop, num_predict), "mode": "BEFORE"})
        report(name, {**run_after(crop, num_predict), "mode": "AFTER"})


if __name__ == "__main__":
    main()


