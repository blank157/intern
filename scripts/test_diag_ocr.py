"""Diagnostic script: test Qwen3-VL OCR on real region crops and inspect segmentation."""

import asyncio
import json
import sys
from pathlib import Path
import httpx
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")

async def test_direct_qwen():
    crop_files = list(Path("temp/test_ui").glob("**/region_crops/*.png"))
    print(f"Found {len(crop_files)} region crops in temp:")
    for cf in crop_files[:5]:
        img = Image.open(cf)
        print(f"  Crop: {cf.name} - size: {img.size} mode: {img.mode}")

    if not crop_files:
        print("No crop files found in temp.")
        return

    test_crop = crop_files[0]
    print(f"\nTesting OCR on {test_crop}...")

    import base64
    with open(test_crop, "rb") as f:
        img_bytes = f.read()
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    data_uri = f"data:image/png;base64,{b64}"

    # Prompt 1: Short direct OCR prompt
    short_prompt = (
        "You are a handwriting OCR system.\n"
        "Transcribe every visible handwritten word in the supplied image exactly as it appears.\n"
        "Output ONLY the transcription. Do not explain."
    )

    # Prompt 2: Full base.txt prompt
    with open("src/answer_eval/prompts/templates/ocr/base.txt", "r", encoding="utf-8") as f:
        full_prompt = f.read()

    async with httpx.AsyncClient(base_url="http://localhost:11434/v1", timeout=60.0) as client:
        # Test with short prompt
        payload_short = {
            "model": "qwen3-vl:4b",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_uri}},
                        {"type": "text", "text": short_prompt},
                    ],
                }
            ],
            "max_tokens": 2048,
            "temperature": 0.0,
            "stream": False,
        }
        
        print("\n--- Sending request with SHORT prompt ---")
        try:
            resp = await client.post("/chat/completions", json=payload_short)
            print(f"HTTP Status: {resp.status_code}")
            data = resp.json()
            choice = data["choices"][0]
            content = choice["message"]["content"]
            print(f"Finish reason: {choice.get('finish_reason')}")
            print(f"Content length: {len(content)}")
            print(f"Content repr: {repr(content)}")
            print(f"Content:\n{content}")
        except Exception as e:
            print(f"Error: {e}")

        # Test with full prompt
        payload_full = {
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
        
        print("\n--- Sending request with FULL prompt ---")
        try:
            resp = await client.post("/chat/completions", json=payload_full)
            print(f"HTTP Status: {resp.status_code}")
            data = resp.json()
            choice = data["choices"][0]
            content = choice["message"]["content"]
            print(f"Finish reason: {choice.get('finish_reason')}")
            print(f"Content length: {len(content)}")
            print(f"Content repr: {repr(content)}")
            print(f"Content:\n{content}")
        except Exception as e:
            print(f"Error: {e}")

asyncio.run(test_direct_qwen())
