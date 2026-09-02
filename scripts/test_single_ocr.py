"""Direct Qwen3-VL OCR Diagnostic on real crop."""

import base64
import sys
import time
from pathlib import Path

import httpx
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")

def main():
    crops = sorted(list(Path("temp/test_ui").glob("**/region_crops/*.png")))
    if not crops:
        print("No crops found.")
        return

    crop_path = crops[0]
    print(f"[1] Testing crop: {crop_path}")
    img = Image.open(crop_path)
    print(f"    Size: {img.size}, Mode: {img.mode}")

    with open(crop_path, "rb") as f:
        img_bytes = f.read()

    b64 = base64.b64encode(img_bytes).decode("utf-8")
    data_uri = f"data:image/png;base64,{b64}"
    print(f"    Base64 length: {len(b64)}")

    prompt = (
        "You are a handwriting transcription system.\n"
        "Transcribe every visible handwritten word in the supplied image exactly as it appears.\n"
        "Output only the transcription."
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
        "max_tokens": 512,
        "temperature": 0.0,
        "stream": False,
    }

    print("[2] Sending request to Ollama http://localhost:11434/v1/chat/completions...")
    t0 = time.perf_counter()
    with httpx.Client(base_url="http://localhost:11434/v1", timeout=60.0) as client:
        resp = client.post("/chat/completions", json=payload)
    dur = time.perf_counter() - t0
    print(f"[3] Response received in {dur:.2f}s, status: {resp.status_code}")

    if resp.status_code == 200:
        data = resp.json()
        choice = data["choices"][0]
        msg = choice.get("message", {})
        content = msg.get("content", "")
        print(f"    Finish reason: {choice.get('finish_reason')}")
        print(f"    Content type: {type(content)}")
        print(f"    Content length: {len(content)}")
        print(f"    Content repr: {repr(content)}")
        print(f"    Raw text:\n{content}")
    else:
        print(f"    Response error: {resp.text}")

if __name__ == "__main__":
    main()
