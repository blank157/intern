"""Inspect the exact JSON response returned by Ollama on REG-P01-01."""

import base64
import json
import sys
from pathlib import Path
import httpx

sys.stdout.reconfigure(encoding="utf-8")

crops = sorted(list(Path("temp/test_e2e_verification/crops").glob("*.png")))
print(f"Found {len(crops)} crops:")
for c in crops:
    print(f"  {c.name}")

if not crops:
    sys.exit(1)

crop_path = crops[0]
with open(crop_path, "rb") as f:
    b64 = base64.b64encode(f.read()).decode("utf-8")
data_uri = f"data:image/png;base64,{b64}"

prompt = (
    "You are a handwriting transcription system.\n\n"
    "Transcribe every visible handwritten word in the supplied image exactly as it appears.\n\n"
    "Rules:\n"
    "- Output only the transcription.\n"
    "- Do not explain.\n"
    "- Do not summarize.\n"
    "- Do not correct spelling.\n"
    "- Do not correct grammar.\n"
    "- Do not complete missing text.\n"
    "- Preserve visible numbers, symbols, and punctuation.\n"
    "- Preserve line breaks and line ordering.\n"
    "- Ignore notebook ruling.\n"
    "- Ignore teacher ticks/correction strokes unless they contain actual readable text.\n"
    "- If text has been crossed out, transcribe it as: [CROSSED OUT: text]\n"
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
                {"type": "text", "text": prompt},
            ],
        }
    ],
    "max_tokens": 4096,
    "temperature": 0.0,
    "stream": False,
}

print("\nSending request to /v1/chat/completions...")
with httpx.Client(base_url="http://localhost:11434/v1", timeout=120.0) as client:
    resp = client.post("/chat/completions", json=payload)

print(f"HTTP Status: {resp.status_code}")
raw_json = resp.json()
print("Raw JSON response keys:", list(raw_json.keys()))
print("Choices structure:")
for i, ch in enumerate(raw_json.get("choices", [])):
    print(f"Choice {i}: finish_reason={ch.get('finish_reason')}")
    msg = ch.get("message", {})
    print(f"  Message keys: {list(msg.keys())}")
    for k, v in msg.items():
        if k == "content":
            print(f"  msg['content'] ({len(v)} chars) = {repr(v)}")
        elif k == "reasoning":
            print(f"  msg['reasoning'] ({len(v)} chars) = {repr(v[:200])}...")
        else:
            print(f"  msg['{k}'] = {repr(v)}")
