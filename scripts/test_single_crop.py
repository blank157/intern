"""Test single column / left half of the duplicate image."""

import base64
import sys
from pathlib import Path
from PIL import Image
import io
import httpx

sys.stdout.reconfigure(encoding="utf-8")

img_path = Path("C:/Users/Administrator/.gemini/antigravity/brain/0ee1b230-9a10-47fd-81ec-88779d770603/.user_uploaded/media_1787319285750.png")
img = Image.open(img_path).convert("RGB")
w, h = img.size
print(f"Full duplicate image: {w}x{h}")

# Crop only the single student writing area (left half)
single_crop = img.crop((0, 0, int(w * 0.48), h))
print(f"Single column crop: {single_crop.size}")

buf = io.BytesIO()
single_crop.save(buf, format="PNG")
b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
data_uri = f"data:image/png;base64,{b64}"

prompt = (
    "Transcribe every visible handwritten word in this image exactly as written. "
    "Output only the verbatim transcription."
)

payload = {
    "model": "qwen3-vl:16k",
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
}

print("\n--- Sending request to Ollama /v1/chat/completions for SINGLE crop ---")
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
