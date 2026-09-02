"""Test Ollama parameter translation for max_tokens vs options num_predict."""

import base64
import sys
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8")

crops = sorted(list(Path("temp/test_e2e_verification/crops").glob("*.png")))
crop_path = crops[0]
with open(crop_path, "rb") as f:
    b64 = base64.b64encode(f.read()).decode("utf-8")
data_uri = f"data:image/png;base64,{b64}"

prompt = "Transcribe the handwriting in this image."

with httpx.Client(base_url="http://localhost:11434", timeout=120.0) as client:
    # Test A: /v1/chat/completions with options num_predict and max_tokens
    print("--- Test A: /v1/chat/completions with max_tokens + options ---")
    payload_a = {
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
        "max_completion_tokens": 4096,
        "options": {
            "num_predict": 4096,
            "num_ctx": 8192,
        },
        "stream": False,
    }
    resp_a = client.post("/v1/chat/completions", json=payload_a)
    data_a = resp_a.json()
    choice_a = data_a["choices"][0]
    print(f"Test A finish_reason: {choice_a.get('finish_reason')}")
    print(f"Test A content len: {len(choice_a['message'].get('content', ''))}")
    print(f"Test A content: {choice_a['message'].get('content', '')[:150]}")

    # Test B: Native /api/chat with options num_predict=4096
    print("\n--- Test B: /api/chat native with num_predict=4096 ---")
    payload_b = {
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
    resp_b = client.post("/api/chat", json=payload_b)
    data_b = resp_b.json()
    msg_b = data_b.get("message", {})
    print(f"Test B done_reason: {data_b.get('done_reason')}")
    print(f"Test B eval_count: {data_b.get('eval_count')}")
    print(f"Test B content len: {len(msg_b.get('content', ''))}")
    print(f"Test B content:\n{msg_b.get('content', '')}")
