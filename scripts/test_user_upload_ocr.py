"""Test OCR on user's newly uploaded image with num_ctx=16384 and smart width scaling."""

import base64
import sys
from pathlib import Path
from PIL import Image
import io
import httpx

sys.stdout.reconfigure(encoding="utf-8")

img_path = Path("C:/Users/Administrator/.gemini/antigravity/brain/0ee1b230-9a10-47fd-81ec-88779d770603/.user_uploaded/media_1787319285750.png")
print(f"Testing uploaded image: {img_path.name}")

img = Image.open(img_path).convert("RGB")
w, h = img.size
print(f"Original size: {w}x{h}")

# Smart scale if > 1280
if w > 1280:
    ratio = 1280.0 / w
    img = img.resize((1280, int(h * ratio)), Image.LANCZOS)
print(f"Scaled size: {img.size}")

buf = io.BytesIO()
img.save(buf, format="PNG")
b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
data_uri = f"data:image/png;base64,{b64}"

prompt = (
    "Transcribe every visible handwritten word in this image exactly as written. "
    "Output only the verbatim transcription."
)

payload = {
    "model": "qwen3-vl:4b",
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_uri}},
                {"type": "text", "text": prompt},
            ],
        }
    ],
    "max_tokens": 4096,
    "temperature": 0.0,
    "stream": False,
    "options": {
        "num_ctx": 16384,
        "num_predict": 4096,
        "temperature": 0.0,
    },
}

print("\n--- Sending request to Ollama /v1/chat/completions with num_ctx=16384 ---")
with httpx.Client(base_url="http://localhost:11434", timeout=120.0) as client:
    resp = client.post("/v1/chat/completions", json=payload)
    print(f"HTTP Status: {resp.status_code}")
    data = resp.json()
    if resp.status_code == 200:
        ch = data["choices"][0]
        content = ch["message"].get("content", "").strip()
        print(f"finish_reason: {ch.get('finish_reason')}")
        print(f"usage: {data.get('usage')}")
        print(f"Transcription:\n{content}")
    else:
        print(f"Error response: {data}")
