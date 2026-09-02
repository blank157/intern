"""Test assistant-prefill '<think></think>' trick and natural thinking convergence."""

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
NP = int(sys.argv[1]) if len(sys.argv) > 1 else 1024

CROPS = {
    "region_01": ROOT / "temp/test_5regions/region_01.png",
    "region_04": ROOT / "temp/test_5regions/region_04.png",
}


def run(label: str, crop: Path, prefill_think_closed: bool) -> None:
    b64 = base64.b64encode(crop.read_bytes()).decode()
    messages = [{"role": "user", "content": PROMPT, "images": [b64]}]
    if prefill_think_closed:
        messages.append({"role": "assistant", "content": "<think>\n\n</think>\n\n"})
    payload = {
        "model": MODEL,
        "messages": messages,
        "think": False,
        "stream": False,
        "options": {"num_ctx": 16384, "num_predict": NP, "temperature": 0},
    }
    t0 = time.perf_counter()
    r = httpx.post(f"{BASE}/api/chat", json=payload, timeout=900)
    dt = time.perf_counter() - t0
    d = r.json()
    msg = d.get("message") or {}
    c = (msg.get("content") or "").strip()
    th = msg.get("thinking") or ""
    print(
        f"{label}: {dt:.1f}s done={d.get('done_reason')} eval={d.get('eval_count')} "
        f"content={len(c)}ch thinking={len(th)}ch",
        flush=True,
    )
    print(f"   preview: {c[:200]!r}", flush=True)
    if th:
        print(f"   think-preview: {th[:100]!r}", flush=True)


if __name__ == "__main__":
    name = sys.argv[2] if len(sys.argv) > 2 else "region_01"
    crop = CROPS[name]
    print(f"=== np={NP} crop={crop.name} ===", flush=True)
    run("plain", crop, False)
    run("prefill_closed_think", crop, True)
