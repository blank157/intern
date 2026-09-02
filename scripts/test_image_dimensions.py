"""Inspect actual image dimensions of pipeline crops vs small crops that work."""

import base64
import sys
from pathlib import Path

import httpx
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")

# Show dimensions of all crops
all_crops = {
    "E2E-pipeline crop": list(Path("temp/test_e2e_verification/crops").glob("*.png")),
    "UI session crops": list(Path("temp/test_ui").glob("**/region_crops/*.png")),
    "5-region test crops": list(Path("temp/test_5regions").glob("*.png")),
}

for label, files in all_crops.items():
    print(f"\n{label}:")
    for f in sorted(files)[:3]:
        img = Image.open(f)
        size_kb = f.stat().st_size // 1024
        print(f"  {f.name}: {img.size[0]}x{img.size[1]} ({size_kb} KB)")

# Test: one of the 5-region crops (regions 1 and 3 which should be smaller)
crops_5r = sorted(list(Path("temp/test_5regions").glob("*.png")))
if not crops_5r:
    print("No 5-region crops found.")
    sys.exit(0)

# Test region 1 (PART-A header, small) and region 3 (Q1 content, large)
test_regions = [crops_5r[0], crops_5r[2]] if len(crops_5r) >= 3 else [crops_5r[0]]

prompt = (
    "Transcribe every visible handwritten word in this image exactly as written. "
    "Output only the verbatim transcription."
)

print("\n--- Testing region crops via /api/chat ---")
with httpx.Client(base_url="http://localhost:11434", timeout=120.0) as client:
    for cp in test_regions:
        img = Image.open(cp)
        print(f"\nCrop: {cp.name} ({img.size[0]}x{img.size[1]})")

        with open(cp, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")

        resp = client.post("/api/chat", json={
            "model": "qwen3-vl:4b",
            "messages": [{"role": "user", "content": prompt, "images": [b64]}],
            "stream": False,
            "options": {"num_predict": 2048, "temperature": 0.0},
        })
        d = resp.json()
        msg = d.get("message", {})
        content = msg.get("content", "").strip()
        thinking = msg.get("thinking", "")
        print(f"  prompt_eval_count: {d.get('prompt_eval_count')}")
        print(f"  eval_count: {d.get('eval_count')}, done_reason: {d.get('done_reason')}")
        print(f"  thinking length: {len(thinking)}")
        print(f"  content length: {len(content)}")
        print(f"  Transcription: {repr(content[:150])}")
