"""Test strip-based OCR: split tall crops into 180px strips, OCR each, concatenate."""

import base64
import sys
from pathlib import Path
from PIL import Image
import io
import httpx

sys.stdout.reconfigure(encoding="utf-8")

MAX_WIDTH = 1024
STRIP_HEIGHT = 180  # max height per strip at 1024 wide
OVERLAP_PX = 15     # small overlap to avoid cutting words

def scale_img(img):
    """Scale to max MAX_WIDTH preserving aspect."""
    w, h = img.size
    if w > MAX_WIDTH:
        ratio = MAX_WIDTH / w
        img = img.resize((MAX_WIDTH, int(h * ratio)), Image.LANCZOS)
    return img

def split_strips(img, strip_h=STRIP_HEIGHT, overlap=OVERLAP_PX):
    """Split image into overlapping horizontal strips."""
    w, h = img.size
    strips = []
    y = 0
    while y < h:
        y_end = min(h, y + strip_h)
        strip = img.crop((0, y, w, y_end))
        strips.append((y, y_end, strip))
        if y_end >= h:
            break
        y = y_end - overlap
    return strips

def encode_img(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

def ocr_crop(client, img, model="qwen3-vl:4b"):
    """OCR a single image crop."""
    prompt = (
        "Transcribe every visible handwritten word in this image exactly as written. "
        "Output only the verbatim transcription."
    )
    resp = client.post("/api/chat", json={
        "model": model,
        "messages": [{"role": "user", "content": prompt, "images": [encode_img(img)]}],
        "stream": False,
        "options": {"num_predict": 2048, "num_ctx": 8192, "temperature": 0.0},
    })
    d = resp.json()
    msg = d.get("message", {})
    content = msg.get("content", "").strip()
    thinking_len = len(msg.get("thinking", ""))
    eval_c = d.get("eval_count")
    done = d.get("done_reason")
    return content, thinking_len, eval_c, done

crops = sorted(list(Path("temp/test_5regions").glob("*.png")))

print("--- Strip-based OCR ---")
with httpx.Client(base_url="http://localhost:11434", timeout=180.0) as client:
    for cp in crops:
        orig = Image.open(cp).convert("RGB")
        scaled = scale_img(orig)
        sw, sh = scaled.size
        print(f"\n{'='*60}")
        print(f"Crop: {cp.name} orig={orig.size} scaled={scaled.size}")

        if sh <= STRIP_HEIGHT:
            # Small enough for single call
            content, think_len, eval_c, done = ocr_crop(client, scaled)
            print(f"  [single] eval={eval_c}, done={done}, thinking={think_len}, content={len(content)}")
            print(f"  Transcription: {repr(content[:300])}")
        else:
            # Split into strips
            strips = split_strips(scaled)
            print(f"  Splitting into {len(strips)} strips of max {STRIP_HEIGHT}px")
            all_text = []
            for i, (y0, y1, strip) in enumerate(strips):
                content, think_len, eval_c, done = ocr_crop(client, strip)
                sw2, sh2 = strip.size
                print(f"  [strip {i+1}/{len(strips)}] y=[{y0}..{y1}] ({sw2}x{sh2}): eval={eval_c}, done={done}, thinking={think_len}, content={len(content)}")
                if content:
                    print(f"    Text: {repr(content[:150])}")
                    all_text.append(content)
            full_text = "\n".join(all_text)
            print(f"\n  FULL TRANSCRIPTION:\n{full_text}")
