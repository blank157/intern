"""Test /nothink prefix (Qwen3 thinking disable) on large crops."""

import base64
import sys
from pathlib import Path
import httpx

sys.stdout.reconfigure(encoding="utf-8")

crops = sorted(list(Path("temp/test_e2e_verification/crops").glob("*.png")))
crop_path = crops[0]  # large region crop
print(f"Testing: {crop_path.name}")

with open(crop_path, "rb") as f:
    b64 = base64.b64encode(f.read()).decode("utf-8")

with httpx.Client(base_url="http://localhost:11434", timeout=120.0) as client:
    # Test A: /nothink prefix in the prompt via /api/chat
    prompt_nothink = (
        "/nothink\n\n"
        "Transcribe every visible handwritten word in this image exactly as written. "
        "Output only the verbatim transcription."
    )
    print("\n--- Test A: /api/chat with /nothink prefix ---")
    resp = client.post("/api/chat", json={
        "model": "qwen3-vl:4b",
        "messages": [{"role": "user", "content": prompt_nothink, "images": [b64]}],
        "stream": False,
        "options": {"num_predict": 2048, "temperature": 0.0},
    })
    d = resp.json()
    content = d.get("message", {}).get("content", "").strip()
    print(f"eval_count: {d.get('eval_count')}, done_reason: {d.get('done_reason')}")
    print(f"content length: {len(content)}")
    print(f"Transcription:\n{content}")

    # Test B: /nothink prefix via /v1/chat/completions
    data_uri = f"data:image/png;base64,{b64}"
    print("\n--- Test B: /v1/chat/completions with /nothink prefix ---")
    resp2 = client.post("/v1/chat/completions", json={
        "model": "qwen3-vl:4b",
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": data_uri}},
            {"type": "text", "text": prompt_nothink},
        ]}],
        "max_tokens": 2048,
        "temperature": 0.0,
        "stream": False,
    })
    d2 = resp2.json()
    ch = d2["choices"][0]
    msg = ch["message"]
    content2 = msg.get("content", "").strip()
    print(f"finish_reason: {ch.get('finish_reason')}, completion_tokens: {d2.get('usage', {}).get('completion_tokens')}")
    print(f"content length: {len(content2)}")
    print(f"Transcription:\n{content2}")
