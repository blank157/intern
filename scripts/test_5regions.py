"""Test natural 4-5 region segmentation + OCR on the real page."""

import asyncio
import base64
import sys
import time
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
import httpx

sys.stdout.reconfigure(encoding="utf-8")

# 1. Load image
test_page_path = list(Path("temp/test_ui").glob("**/rendered_pages/*.png"))[0]
img = Image.open(test_page_path).convert("RGB")
w, h = img.size
print(f"Page image: {test_page_path.name} ({w}x{h})")

gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
_, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

# 2. Projection profile
row_sums = np.sum(thresh == 255, axis=1) / float(w)
is_active = row_sums > 0.0015

raw_bands = []
in_band = False
start_y = 0
for y, active in enumerate(is_active):
    if active and not in_band:
        in_band = True
        start_y = y
    elif not active and in_band:
        in_band = False
        band_ink = np.sum(thresh[start_y:y, :] == 255)
        if band_ink >= 50:
            raw_bands.append((start_y, y))
if in_band:
    raw_bands.append((start_y, h))

print(f"Raw active bands: {len(raw_bands)}")

# 3. Merge with gap_px = 35px (~1% of 3509px height)
# Gaps between paragraphs on this page:
# Q1 Bagging def -> Q1 continuation: gap=21px (merged)
# Q1 continuation -> Q1 example (* Random Forest): gap=80px (SPLIT!)
# Q1 example -> Q2 Random Forest: gap=105px (SPLIT!)
# Q2 def -> Q2 continuation: gap=42px / 35px
gap_threshold = 30
merged = []
curr_s, curr_e = raw_bands[0]
for ns, ne in raw_bands[1:]:
    if (ns - curr_e) <= gap_threshold:
        curr_e = ne
    else:
        merged.append((curr_s, curr_e))
        curr_s, curr_e = ns, ne
merged.append((curr_s, curr_e))

# Filter margin rules (y < 0.08 or y > 0.98 with height < 15px)
filtered = []
for sy, ey in merged:
    bh = ey - sy
    if bh < 15 and (ey / float(h) < 0.08 or sy / float(h) > 0.96):
        continue
    filtered.append((sy, ey))

print(f"\nFinal Segmented Regions: {len(filtered)}")
out_dir = Path("temp/test_5regions")
out_dir.mkdir(parents=True, exist_ok=True)

crops = []
for i, (sy, ey) in enumerate(filtered, 1):
    pad = int(h * 0.008)
    ymin = max(0, sy - pad)
    ymax = min(h, ey + pad)
    crop = img.crop((0, ymin, w, ymax))
    cp = out_dir / f"region_{i:02d}.png"
    crop.save(cp)
    crops.append((i, cp, ymin/h, ymax/h))
    print(f"  Region {i}: y=[{ymin:4d}..{ymax:4d}] (norm [{ymin/h:.3f}..{ymax/h:.3f}], h={ymax-ymin:3d}px)")

# 4. Run native /api/chat OCR on all regions
prompt = (
    "Transcribe every visible handwritten word in this image exactly as written. "
    "Output only the verbatim transcription."
)

print("\n--- Running OCR on all regions ---")
with httpx.Client(base_url="http://localhost:11434", timeout=120.0) as client:
    for idx, cp, ymin, ymax in crops:
        print(f"\n[OCR Region {idx}] y=[{ymin:.3f}..{ymax:.3f}]:")
        with open(cp, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")

        payload = {
            "model": "qwen3-vl:4b",
            "messages": [{"role": "user", "content": prompt, "images": [b64]}],
            "stream": False,
            "options": {"num_predict": 2048, "temperature": 0.0},
        }
        t0 = time.perf_counter()
        resp = client.post("/api/chat", json=payload)
        dur = time.perf_counter() - t0
        data = resp.json()
        content = data.get("message", {}).get("content", "").strip()
        print(f"  Done in {dur:.2f}s, eval_count: {data.get('eval_count')}")
        print(f"  Transcription:\n{content}")
