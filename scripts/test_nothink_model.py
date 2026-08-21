"""Create no-thinking Qwen3-VL model via Ollama REST API, then test OCR."""

import base64
import sys
import json
from pathlib import Path
from PIL import Image
import io
import httpx

sys.stdout.reconfigure(encoding="utf-8")

# First, create the no-thinking model via Ollama API
modelfile = "FROM qwen3-vl:4b\nPARAMETER thinking false\n"
print("Creating qwen3-vl-nothink model...")
with httpx.Client(base_url="http://localhost:11434", timeout=120.0) as client:
    resp = client.post("/api/create", json={
        "name": "qwen3-vl-nothink",
        "modelfile": modelfile,
        "stream": False,
    })
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text[:500]}")

print("\nModel creation done. Now testing OCR...")

MAX_WIDTH = 1024
MIN_HEIGHT = 40

def encode_crop(path):
    img = Image.open(path).convert("RGB")
    w, h = img.size
    if w > MAX_WIDTH:
        new_h = int(h * MAX_WIDTH / w)
        if new_h >= MIN_HEIGHT:
            img = img.resize((MAX_WIDTH, new_h), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8"), img.size

crops = sorted(list(Path("temp/test_5regions").glob("*.png")))
prompt = (
    "Transcribe every visible handwritten word in this image exactly as written. "
    "Output only the verbatim transcription."
)

with httpx.Client(base_url="http://localhost:11434", timeout=180.0) as client:
    for cp in crops:
        orig = Image.open(cp)
        b64, new_size = encode_crop(cp)
        print(f"\nCrop: {cp.name} orig={orig.size} -> {new_size}")
        resp = client.post("/api/chat", json={
            "model": "qwen3-vl-nothink",
            "messages": [{"role": "user", "content": prompt, "images": [b64]}],
            "stream": False,
            "options": {"num_predict": 2048, "num_ctx": 8192, "temperature": 0.0},
        })
        d = resp.json()
        msg = d.get("message", {})
        content = msg.get("content", "").strip()
        thinking_len = len(msg.get("thinking", ""))
        print(f"  prompt_eval: {d.get('prompt_eval_count')}, eval: {d.get('eval_count')}, done: {d.get('done_reason')}")
        print(f"  thinking_len: {thinking_len}, content_len: {len(content)}")
        print(f"  Transcription: {repr(content[:300])}")
