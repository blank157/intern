"""Find which mechanism actually disables Qwen3-VL thinking on installed Ollama."""

import base64
import sys
import time
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
MODEL = sys.argv[2] if len(sys.argv) > 2 else "qwen3-vl:4b"
BASE = "http://localhost:11434"
PROMPT = (ROOT / "src/answer_eval/prompts/templates/ocr/base.txt").read_text(encoding="utf-8")
CROP = ROOT / "temp/test_5regions/region_04.png"
NP = int(sys.argv[1]) if len(sys.argv) > 1 else 384


def native(label: str, think: bool | None = None, mode: str = "plain") -> None:
    b64 = base64.b64encode(CROP.read_bytes()).decode()
    content = PROMPT
    if mode == "prefix":
        content = "/nothink\n\n" + PROMPT
    elif mode == "suffix":
        content = PROMPT + "\n/nothink"
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": content, "images": [b64]}],
        "stream": False,
        "options": {"num_ctx": 16384, "num_predict": NP, "temperature": 0},
    }
    if think is not None:
        payload["think"] = think
    t0 = time.perf_counter()
    r = httpx.post(f"{BASE}/api/chat", json=payload, timeout=600)
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
    print(f"   preview: {c[:120]!r}", flush=True)


if __name__ == "__main__":
    print(f"=== num_predict={NP} crop={CROP.name} model={MODEL} ===", flush=True)
    native("native/plain", None, "plain")
    native("native/think_false_suffix_nothink", False, "suffix")

