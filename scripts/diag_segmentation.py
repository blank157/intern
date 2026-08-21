"""Diagnostic script: inspect segmentation splitting on the actual rendered page."""

import sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")

def diagnose_page_segmentation():
    rendered_pages = list(Path("temp/test_ui").glob("**/rendered_pages/*.png"))
    print(f"Found {len(rendered_pages)} rendered pages in temp:")
    for rp in rendered_pages:
        print(f"  {rp}")

    if not rendered_pages:
        return

    test_page_path = rendered_pages[0]
    print(f"\nAnalyzing page: {test_page_path}")
    img = Image.open(test_page_path).convert("RGB")
    w, h = img.size
    print(f"Image dimensions: {w} x {h}")

    gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    row_sums = np.sum(thresh == 255, axis=1) / float(w)
    print(f"Row sums max: {np.max(row_sums):.4f}, mean: {np.mean(row_sums):.4f}, median: {np.median(row_sums):.4f}")

    for ethresh in [0.01, 0.005, 0.002, 0.001]:
        active_count = np.sum(row_sums > ethresh)
        print(f"  energy_threshold={ethresh}: active rows={active_count}/{h} ({active_count/h*100:.1f}%)")

    # Let's find all contiguous ink bands with lower energy threshold and min gap
    min_gap_px = 30
    energy_threshold = 0.002
    is_active = row_sums > energy_threshold
    raw_blocks = []
    in_block = False
    start_y = 0

    for y, active in enumerate(is_active):
        if active and not in_block:
            in_block = True
            start_y = y
        elif not active and in_block:
            in_block = False
            raw_blocks.append((start_y, y))
    if in_block:
        raw_blocks.append((start_y, h))

    print(f"\nRaw ink bands (energy_threshold={energy_threshold}): {len(raw_blocks)} bands found:")
    for i, (sy, ey) in enumerate(raw_blocks):
        bh = ey - sy
        rel_sy = sy / h
        rel_ey = ey / h
        rel_bh = bh / h
        band_ink = np.sum(thresh[sy:ey, :] == 255)
        print(f"  Band {i+1}: y=[{sy}..{ey}] (norm [{rel_sy:.3f}..{rel_ey:.3f}], height={bh}px / {rel_bh:.3f}) ink_px={band_ink}")

    # Now let's merge with min_gap_px
    merged = []
    if raw_blocks:
        curr_s, curr_e = raw_blocks[0]
        for ns, ne in raw_blocks[1:]:
            if (ns - curr_e) < min_gap_px:
                curr_e = ne
            else:
                merged.append((curr_s, curr_e))
                curr_s, curr_e = ns, ne
        merged.append((curr_s, curr_e))

    print(f"\nMerged blocks (gap < {min_gap_px}px): {len(merged)} blocks:")
    for i, (sy, ey) in enumerate(merged):
        bh = ey - sy
        rel_sy = sy / h
        rel_ey = ey / h
        rel_bh = bh / h
        print(f"  Block {i+1}: y=[{sy}..{ey}] (norm [{rel_sy:.3f}..{rel_ey:.3f}], height={bh}px / {rel_bh:.3f})")

diagnose_page_segmentation()
