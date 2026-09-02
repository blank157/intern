"""Diagram extraction for answer keys.

Renders source pages to images, finds diagram-like regions with the existing
Module-6 segmenter, and crops them from the ORIGINAL page image. Crops are
primary evidence; any text description is auxiliary metadata only.
"""

from __future__ import annotations

import io
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from answer_eval.answerkey.converters import SourceDocument
from answer_eval.processing.image.preprocessing import ImagePreprocessor
from answer_eval.processing.pdf.processor import PDFProcessor
from answer_eval.processing.segmentation.schemas import RegionType
from answer_eval.processing.segmentation.segmenter import QuestionSegmenter

logger = logging.getLogger(__name__)


@dataclass
class DiagramCrop:
    page: int
    ordinal_on_page: int
    png_bytes: bytes
    bbox: list[float]
    confidence: float


def _pil_to_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def extract_diagram_crops(
    document: SourceDocument,
    original_pdf_bytes: bytes | None = None,
    *,
    min_confidence: float = 0.55,
) -> list[DiagramCrop]:
    """Detect + crop diagram regions from every rendered page."""
    preprocessor = ImagePreprocessor()
    segmenter = QuestionSegmenter()
    crops: list[DiagramCrop] = []

    pages: list[tuple[int, Image.Image]] = []
    if document.format == "pdf":
        if original_pdf_bytes is None:
            return crops
        import fitz

        processor = PDFProcessor(default_dpi=200)
        with tempfile.TemporaryDirectory(prefix="evalai-key-") as tmp:
            pdf_path = Path(tmp) / "key.pdf"
            pdf_path.write_bytes(original_pdf_bytes)
            doc = fitz.open(str(pdf_path))
            try:
                for index in range(doc.page_count):
                    _, pil_image = processor.render_page(
                        doc, index + 1, submission_id="answer-key", pdf_path=str(pdf_path), save_to_disk=False
                    )
                    pages.append((index + 1, pil_image))
            finally:
                doc.close()
    else:
        for page in document.pages:
            if not page.image_bytes:
                continue
            pages.append((page.page_number, Image.open(io.BytesIO(page.image_bytes))))

    import hashlib

    from answer_eval.processing.pdf.schemas import PageImage

    with tempfile.TemporaryDirectory(prefix="evalai-key-crops-") as workdir:
        for page_number, image in pages:
            png_bytes = _pil_to_png(image)
            image_file = Path(workdir) / f"page-{page_number}.png"
            image_file.write_bytes(png_bytes)
            page_image = PageImage(
                submission_id=f"answer-key-p{page_number}",
                page_number=page_number,
                width_px=image.width,
                height_px=image.height,
                dpi=200,
                pdf_path="(rendered)",
                image_path=str(image_file),
                page_hash=hashlib.sha256(png_bytes).hexdigest(),
                file_size_bytes=len(png_bytes),
            )
            # Segmenter reads the preprocessed artifact from disk; keep files
            # inside the scoped workdir (auto-cleaned).
            preprocessed = preprocessor.preprocess_page(page_image, save_to_disk=True)
            result = segmenter.segment_page(preprocessed, save_crops=False)
            ordinal = 0
            for region in result.regions:
                if region.region_type not in (RegionType.DIAGRAM, RegionType.MIXED):
                    continue
                if (region.classification_confidence or 0.0) < min_confidence:
                    continue
                x_min, y_min, x_max, y_max = region.bbox.to_pixel_coords(image.width, image.height)
                pad_x = max(4, int((x_max - x_min) * 0.02))
                pad_y = max(4, int((y_max - y_min) * 0.02))
                box = (
                    max(0, x_min - pad_x),
                    max(0, y_min - pad_y),
                    min(image.width, x_max + pad_x),
                    min(image.height, y_max + pad_y),
                )
                if box[2] - box[0] < 24 or box[3] - box[1] < 24:
                    continue
                ordinal += 1
                crop_image = image.crop(box)
                crops.append(
                    DiagramCrop(
                        page=page_number,
                        ordinal_on_page=ordinal,
                        png_bytes=_pil_to_png(crop_image),
                        bbox=[round(v, 4) for v in region.bbox.model_dump().values()],
                        confidence=float(region.classification_confidence or 0.0),
                    )
                )
    logger.info("extracted %d diagram crop(s) from answer key", len(crops))
    return crops
