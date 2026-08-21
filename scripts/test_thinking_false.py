"""Verify that thinking=false disables Qwen3-VL internal reasoning for OCR."""

import base64
import sys
from pathlib import Path
import httpx

sys.stdout.reconfigure(encoding="utf-8")

# Use the large region crop that was producing empty output
crops = sorted(list(Path("temp/test_e2e_verification/crops").glob("*.png")))
crop_path = crops[0]  # REG-P01-01 - was always empty
print(f"Testing: {crop_path.name}")

with open(crop_path, "rb") as f:
    b64 = base64.b64encode(f.read()).decode("utf-8")

prompt = (
    "Transcribe every visible handwritten word in this image exactly as written. "
    "Output only the verbatim transcription."
)

with httpx.Client(base_url="http://localhost:11434", timeout=120.0) as client:
    # Test: /api/chat with thinking=false
    print("\n--- Test: /api/chat with thinking=false ---")
    payload = {
        "model": "qwen3-vl:4b",
        "messages": [{"role": "user", "content": prompt, "images": [b64]}],
        "stream": False,
        "options": {
            "num_predict": 2048,
            "temperature": 0.0,
            "thinking": False,
        },
    }
    resp = client.post("/api/chat", json=payload)
    data = resp.json()
    content = data.get("message", {}).get("content", "").strip()
    print(f"eval_count: {data.get('eval_count')}")
    print(f"done_reason: {data.get('done_reason')}")
    print(f"content length: {len(content)}")
    print(f"Transcription:\n{content}")

    # Also test via /v1/chat/completions with thinking=false
    print("\n--- Test: /v1/chat/completions with thinking=false ---")
    data_uri = f"data:image/png;base64,{b64}"
    payload2 = {
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
        "max_tokens": 2048,
        "temperature": 0.0,
        "stream": False,
        "options": {"thinking": False},
    }
    resp2 = client.post("/v1/chat/completions", json=payload2)
    data2 = resp2.json()
    ch = data2["choices"][0]
    content2 = ch["message"].get("content", "")
    print(f"finish_reason: {ch.get('finish_reason')}")
    print(f"content length: {len(content2)}")
    print(f"Transcription:\n{content2}")
