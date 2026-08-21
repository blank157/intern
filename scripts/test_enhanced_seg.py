"""Test improved segmentation with adaptive merging and coverage validation."""

import sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")

def test_enhanced_segmentation():
    rendered_pages = list(Path("temp/test_ui").glob("**/rendered_pages/*.png"))
    test_page_path = rendered_pages[0]
    img = Image.open(test_page_path).convert("RGB")
    w, h = img.size
    print(f"Page: {test_page_path.name}, Size: {w} x {h}")

    gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # 1. Horizontal projection profile
    row_sums = np.sum(thresh == 255, axis=1) / float(w)
    energy_threshold = 0.0015
    is_active = row_sums > energy_threshold

    # Find raw active bands
    raw_bands = []
    in_band = False
    start_y = 0
    for y, active in enumerate(is_active):
        if active and not in_band:
            in_band = True
            start_y = y
        elif not active and in_band:
            in_band = False
            # Check minimal ink count inside band
            band_ink = np.sum(thresh[start_y:y, :] == 255)
            if band_ink > 100:  # ignore 1-2 rogue noise pixels
                raw_bands.append((start_y, y))
    if in_band:
        raw_bands.append((start_y, h))

    print(f"\nRaw bands found: {len(raw_bands)}")

    # 2. Merge adjacent bands with gap < line_gap_threshold (e.g. 70px ~ 2% of page height)
    merge_gap_px = int(h * 0.02)  # ~70px on 3509px page
    merged_blocks = []
    if raw_bands:
        curr_s, curr_e = raw_bands[0]
        for ns, ne in raw_bands[1:]:
            gap = ns - curr_e
            if gap <= merge_gap_px:
                curr_e = ne
            else:
                merged_blocks.append((curr_s, curr_e))
                curr_s, curr_e = ns, ne
        merged_blocks.append((curr_s, curr_e))

    print(f"\nMerged blocks (gap <= {merge_gap_px}px): {len(merged_blocks)}")
    for i, (sy, ey) in enumerate(merged_blocks, 1):
        bh = ey - sy
        rel_sy = sy / h
        rel_ey = ey / h
        band_ink = np.sum(thresh[sy:ey, :] == 255)
        print(f"  Region {i}: y=[{sy}..{ey}] (norm [{rel_sy:.3f}..{rel_ey:.3f}], height={bh}px / {bh/h:.3f}) ink_px={band_ink}")

    # 3. Coverage validation: check remaining ink
    covered_mask = np.zeros_like(thresh)
    for sy, ey in merged_blocks:
        covered_mask[sy:ey, :] = 255

    uncovered_ink = np.sum((thresh == 255) & (covered_mask == 0))
    total_ink = np.sum(thresh == 255)
    coverage_pct = (total_ink - uncovered_ink) / total_ink * 100
    print(f"\nInk Coverage: {coverage_pct:.2f}% (uncovered: {uncovered_ink}/{total_ink} px)")

test_enhanced_segmentation()
