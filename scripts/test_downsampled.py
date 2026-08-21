"""Test: downsample large crops to max_width=1024 before OCR."""

import base64
import sys
from pathlib import Path
from PIL import Image
import io
import httpx

sys.stdout.reconfigure(encoding="utf-8")

crops_5r = sorted(list(Path("temp/test_5regions").glob("*.png")))
out_dir = Path("temp/test_downsampled")
out_dir.mkdir(parents=True, exist_ok=True)

MAX_WIDTH = 1024  # Qwen3-VL 4B sweet spot

def encode_crop(path, max_width=MAX_WIDTH):
    img = Image.open(path).convert("RGB")
    w, h = img.size
    if w > max_width:
        ratio = max_width / w
        new_w = max_width
        new_h = int(h * ratio)
        img = img.resize((new_w, new_h), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8"), img.size

prompt = (
    "Transcribe every visible handwritten word in this image exactly as written. "
    "Output only the verbatim transcription."
)

print("--- Testing downsampled crops via /api/chat ---")
with httpx.Client(base_url="http://localhost:11434", timeout=120.0) as client:
    for cp in crops_5r:
        orig = Image.open(cp)
        b64, new_size = encode_crop(cp)
        print(f"\nCrop: {cp.name} orig={orig.size[0]}x{orig.size[1]} -> {new_size[0]}x{new_size[1]}")

        resp = client.post("/api/chat", json={
            "model": "qwen3-vl:4b",
            "messages": [{"role": "user", "content": prompt, "images": [b64]}],
            "stream": False,
            "options": {"num_predict": 2048, "temperature": 0.0},
        })
        d = resp.json()
        msg = d.get("message", {})
        content = msg.get("content", "").strip()
        thinking_len = len(msg.get("thinking", ""))
        print(f"  prompt_eval_count: {d.get('prompt_eval_count')}, eval_count: {d.get('eval_count')}, done_reason: {d.get('done_reason')}")
        print(f"  thinking_len: {thinking_len}, content_len: {len(content)}")
        print(f"  Transcription: {repr(content[:200])}")
