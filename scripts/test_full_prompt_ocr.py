"""Test full base.txt prompt with max_tokens=2048."""

import base64
import sys
from pathlib import Path
import httpx

sys.stdout.reconfigure(encoding="utf-8")

crops = sorted(list(Path("temp/test_ui").glob("**/region_crops/*.png")))
crop_path = crops[0]

with open(crop_path, "rb") as f:
    b64 = base64.b64encode(f.read()).decode("utf-8")
data_uri = f"data:image/png;base64,{b64}"

with open("src/answer_eval/prompts/templates/ocr/base.txt", "r", encoding="utf-8") as f:
    full_prompt = f.read()

payload = {
    "model": "qwen3-vl:4b",
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_uri}},
                {"type": "text", "text": full_prompt},
            ],
        }
    ],
    "max_tokens": 2048,
    "temperature": 0.0,
    "stream": False,
}

print("Sending request with full base.txt and max_tokens=2048...")
with httpx.Client(base_url="http://localhost:11434/v1", timeout=60.0) as client:
    resp = client.post("/chat/completions", json=payload)
data = resp.json()
print("Usage:", data.get("usage"))
choice = data["choices"][0]
print("Finish reason:", choice.get("finish_reason"))
msg = choice.get("message", {})
print("Content repr:", repr(msg.get("content")))
print("Content:\n", msg.get("content"))
