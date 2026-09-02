"""Test fix: max_width=1024 + num_predict=4096 on large crop, and original height for thin crops."""

import base64
import io
import sys
from pathlib import Path

import httpx
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")

crops_5r = sorted(list(Path("temp/test_5regions").glob("*.png")))

MAX_WIDTH = 1024
MIN_HEIGHT_FOR_SCALE = 40  # Don't scale below this height

def encode_crop_smart(path):
    img = Image.open(path).convert("RGB")
    w, h = img.size
    if w > MAX_WIDTH:
        ratio = MAX_WIDTH / w
        new_w = MAX_WIDTH
        new_h = int(h * ratio)
        # Don't resize if resulting height would be < MIN_HEIGHT_FOR_SCALE
        if new_h < MIN_HEIGHT_FOR_SCALE:
            # Keep original - don't scale this tiny crop
            pass
        else:
            img = img.resize((new_w, new_h), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8"), img.size

prompt = (
    "Transcribe every visible handwritten word in this image exactly as written. "
    "Output only the verbatim transcription."
)

print("--- Testing smart downsample + num_predict=4096 ---")
with httpx.Client(base_url="http://localhost:11434", timeout=180.0) as client:
    for cp in crops_5r:
        orig = Image.open(cp)
        b64, new_size = encode_crop_smart(cp)
        print(f"\nCrop: {cp.name} orig={orig.size[0]}x{orig.size[1]} -> {new_size[0]}x{new_size[1]}")

        resp = client.post("/api/chat", json={
            "model": "qwen3-vl:4b",
            "messages": [{"role": "user", "content": prompt, "images": [b64]}],
            "stream": False,
            "options": {
                "num_predict": 4096,
                "num_ctx": 8192,
                "temperature": 0.0,
            },
        })
        d = resp.json()
        msg = d.get("message", {})
        content = msg.get("content", "").strip()
        thinking_len = len(msg.get("thinking", ""))
        print(f"  prompt_eval: {d.get('prompt_eval_count')}, eval: {d.get('eval_count')}, done: {d.get('done_reason')}")
        print(f"  thinking_len: {thinking_len}, content_len: {len(content)}")
        print(f"  Transcription: {repr(content[:300])}")
