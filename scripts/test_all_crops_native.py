"""Test native Ollama /api/chat on both crops."""

import base64
import sys
from pathlib import Path
import httpx

sys.stdout.reconfigure(encoding="utf-8")

crops = sorted(list(Path("temp/test_e2e_verification/crops").glob("*.png")))
print(f"Testing {len(crops)} crops with /api/chat...")

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
