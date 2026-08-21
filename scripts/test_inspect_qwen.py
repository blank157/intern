"""Deep inspection of Qwen3-VL response on region crop."""

import base64
import json
import sys
import time
from pathlib import Path
import httpx

sys.stdout.reconfigure(encoding="utf-8")

def main():
    crops = sorted(list(Path("temp/test_ui").glob("**/region_crops/*.png")))
    crop_path = crops[0]

    with open(crop_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    data_uri = f"data:image/png;base64,{b64}"

    with httpx.Client(base_url="http://localhost:11434/v1", timeout=60.0) as client:
        # Test 1: max_tokens = 2048 with /v1/chat/completions
        print("\n=== Test 1: /v1/chat/completions max_tokens=2048 ===")
        payload = {
            "model": "qwen3-vl:4b",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_uri}},
                        {"type": "text", "text": "Transcribe the text in this image."},
                    ],
                }
            ],
            "max_tokens": 2048,
            "temperature": 0.0,
            "stream": False,
        }
        resp = client.post("/chat/completions", json=payload)
        data = resp.json()
        print("Usage:", data.get("usage"))
        choice = data["choices"][0]
        print("Finish reason:", choice.get("finish_reason"))
        msg = choice.get("message", {})
        print("Message keys:", msg.keys())
        print("Content repr:", repr(msg.get("content")))
        if "thinking" in msg:
            print("Thinking repr:", repr(msg.get("thinking")))

        # Test 2: Ollama native /api/chat endpoint
        print("\n=== Test 2: Native Ollama /api/chat ===")
        native_payload = {
            "model": "qwen3-vl:4b",
            "messages": [
                {
                    "role": "user",
                    "content": "Transcribe the text in this image.",
                    "images": [b64],
                }
            ],
            "stream": False,
            "options": {
                "num_predict": 2048,
                "temperature": 0.0,
            }
        }
        resp2 = httpx.post("http://localhost:11434/api/chat", json=native_payload, timeout=60.0)
        data2 = resp2.json()
        print("Native message:", data2.get("message"))
        print("Native done_reason:", data2.get("done_reason"))
        print("Native eval_count:", data2.get("eval_count"))
        print("Native prompt_eval_count:", data2.get("prompt_eval_count"))

if __name__ == "__main__":
    main()
