"""Test direct OCR prompt on both crops."""

import base64
import sys
from pathlib import Path
import httpx

sys.stdout.reconfigure(encoding="utf-8")

crops = sorted(list(Path("temp/test_e2e_verification/crops").glob("*.png")))
prompt = "Transcribe every visible handwritten word in this image exactly as written. Output only the verbatim transcription."

with httpx.Client(base_url="http://localhost:11434", timeout=120.0) as client:
    for idx, cp in enumerate(crops, start=1):
        print(f"\n==========================================")
        print(f"CROP {idx}: {cp.name}")
        print(f"==========================================")
        with open(cp, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")

        payload = {
            "model": "qwen3-vl:4b",
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [b64],
                }
            ],
            "stream": False,
            "options": {
                "num_predict": 4096,
                "num_ctx": 8192,
                "temperature": 0.0,
            },
        }

        resp = client.post("/api/chat", json=payload)
        data = resp.json()
        msg = data.get("message", {})
        content = msg.get("content", "")
        print(f"eval_count: {data.get('eval_count')}")
        print(f"done_reason: {data.get('done_reason')}")
        print(f"content length: {len(content)}")
        print(f"Transcription:\n{content}")
