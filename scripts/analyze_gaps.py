"""Inspect all bands and question markers on the page."""

import sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")

def analyze_bands():
    test_page_path = list(Path("temp/test_ui").glob("**/rendered_pages/*.png"))[0]
    img = Image.open(test_page_path).convert("RGB")
    w, h = img.size

    gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

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
            if band_ink > 100:
                raw_bands.append((start_y, y))
    if in_band:
        raw_bands.append((start_y, h))

    print(f"Total raw bands: {len(raw_bands)}")
    for idx, (sy, ey) in enumerate(raw_bands, 1):
        gap_to_next = raw_bands[idx][0] - ey if idx < len(raw_bands) else 0
        print(f"  Band {idx:02d}: y=[{sy:4d}..{ey:4d}] (norm [{sy/h:.3f}..{ey/h:.3f}], h={ey-sy:3d}px) -> gap to next: {gap_to_next:3d}px")

analyze_bands()
