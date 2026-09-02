"""Test Crop 3 with max_tokens=4096."""

import base64
import sys
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8")

crops = sorted(list(Path("temp/test_ui").glob("**/region_crops/*.png")))
crop_path = crops[2]  # Crop 3

with open(crop_path, "rb") as f:
    b64 = base64.b64encode(f.read()).decode("utf-8")
data_uri = f"data:image/png;base64,{b64}"

concise_prompt = (
    "You are a handwriting transcription system.\n\n"
    "Transcribe every visible handwritten word in the supplied image exactly as it appears.\n\n"
    "Rules:\n"
    "- Output only the transcription.\n"
    "- Do not explain.\n"
    "- Do not summarize.\n"
    "- Do not correct spelling.\n"
    "- Do not correct grammar.\n"
    "- Do not complete missing text.\n"
    "- Preserve visible numbers and punctuation.\n"
    "- Preserve line ordering.\n"
    "- Ignore notebook ruling.\n"
    "- Ignore teacher ticks/correction strokes unless they contain actual readable text.\n"
    "- If a word genuinely cannot be read, output [ILLEGIBLE].\n"
    "- Never return an empty response when readable handwriting is visible."
)

payload = {
    "model": "qwen3-vl:4b",
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_uri}},
                {"type": "text", "text": concise_prompt},
            ],
        }
    ],
    "max_tokens": 4096,
    "temperature": 0.0,
    "stream": False,
}

print(f"Testing Crop 3 ({crop_path.name}) with max_tokens=4096...")
with httpx.Client(base_url="http://localhost:11434/v1", timeout=120.0) as client:
    resp = client.post("/chat/completions", json=payload)
data = resp.json()
choice = data["choices"][0]
msg = choice.get("message", {})
content = msg.get("content", "")
print("Usage:", data.get("usage"))
print("Finish reason:", choice.get("finish_reason"))
print("Content length:", len(content))
print("Transcription:\n", content)
