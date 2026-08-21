"""Unit tests for Module 6: Question Segmentation and Layout Region Classification."""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from answer_eval.processing.image.schemas import ImageQualityMetrics, PreprocessedPage
from answer_eval.processing.segmentation.schemas import (
    BoundingBox,
    PageSegmentationResult,
    RegionType,
)
from answer_eval.processing.segmentation.segmenter import QuestionSegmenter


def test_bounding_box_coordinates() -> None:
    bbox = BoundingBox(x_min=0.1, y_min=0.2, x_max=0.9, y_max=0.8)
    left, top, right, bottom = bbox.to_pixel_coords(width=1000, height=2000)
    assert left == 100
    assert top == 400
    assert right == 900
    assert bottom == 1600


def test_question_segmentation(sample_image: Image.Image, temp_workspace: Path) -> None:
    img_path = temp_workspace / "prep_page.png"
    sample_image.save(img_path)

    prep_page = PreprocessedPage(
        submission_id="SUB-01",
        page_number=1,
        original_image_path=str(img_path),
        original_page_hash="orig_hash",
        preprocessed_image_path=str(img_path),
        preprocessed_page_hash="prep_hash",
        width_px=sample_image.width,
        height_px=sample_image.height,
        quality_metrics=ImageQualityMetrics(
            blur_score=150.0,
            brightness_score=200.0,
            contrast_score=50.0,
        ),
    )

    segmenter = QuestionSegmenter(crops_output_dir=temp_workspace / "crops")
    result = segmenter.segment_page(prep_page)

    assert isinstance(result, PageSegmentationResult)
    assert result.submission_id == "SUB-01"
    assert result.page_number == 1
    assert len(result.regions) >= 1

    for reg in result.regions:
        assert reg.region_id.startswith("REG-P01-")
        assert reg.reading_order >= 1
        assert reg.bbox.x_min >= 0.0 and reg.bbox.x_max <= 1.0
        assert reg.bbox.y_min >= 0.0 and reg.bbox.y_max <= 1.0
        assert 0.0 <= reg.classification_confidence <= 1.0
        assert Path(reg.crop_image_path).exists()
        assert len(reg.crop_image_hash) == 64


def test_classify_handwritten_text_alone(temp_workspace: Path) -> None:
    """Test A: Handwritten text lines alone are classified as ANSWER_TEXT."""
    img = Image.new("RGB", (600, 300), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    # Simulate horizontal lines of handwriting text
    for y in range(40, 260, 40):
        draw.text((50, y), f"This is line of student handwritten answer text at y={y}", fill=(20, 20, 20))

    img_np = np.array(img)
    gray = np.array(img.convert("L"))

    segmenter = QuestionSegmenter(crops_output_dir=temp_workspace / "crops")
    region_type, conf = segmenter._classify_region_content(gray, img_np)

    assert region_type == RegionType.ANSWER_TEXT
    assert conf >= 0.5


def test_classify_handwritten_text_with_red_teacher_marks(temp_workspace: Path) -> None:
    """Test B: Handwritten text with red teacher check marks/underlines is NOT a diagram."""
    img = Image.new("RGB", (600, 300), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    # Handwriting text
    draw.text((50, 50), "are combined to improve accuracy and", fill=(10, 10, 10))
    draw.text((50, 90), "reduce overfitting.", fill=(10, 10, 10))
    draw.text((50, 150), "Example: Random Forest combining Decision Trees", fill=(10, 10, 10))

    # Red teacher check marks (✓) and red underline
    draw.line([(400, 60), (415, 80), (445, 45)], fill=(220, 30, 30), width=4)
    draw.line([(50, 115), (200, 115)], fill=(220, 30, 30), width=3)
    draw.line([(480, 160), (495, 180), (525, 145)], fill=(220, 30, 30), width=4)

    img_np = np.array(img)
    gray = np.array(img.convert("L"))

    segmenter = QuestionSegmenter(crops_output_dir=temp_workspace / "crops")
    region_type, conf = segmenter._classify_region_content(gray, img_np)

    assert region_type == RegionType.ANSWER_TEXT, (
        f"Expected ANSWER_TEXT but got {region_type} with conf {conf}"
    )


def test_classify_arrow_bullet_points(temp_workspace: Path) -> None:
    """Test C: Arrow bullets in handwriting (-> or =>) are NOT classified as diagrams."""
    img = Image.new("RGB", (600, 300), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((50, 40), "-> Point 1: Supervised learning requires labeled data", fill=(15, 15, 15))
    draw.text((50, 90), "-> Point 2: Unsupervised learning finds hidden patterns", fill=(15, 15, 15))
    draw.text((50, 140), "=> Point 3: Reinforcement learning uses rewards", fill=(15, 15, 15))

    img_np = np.array(img)
    gray = np.array(img.convert("L"))

    segmenter = QuestionSegmenter(crops_output_dir=temp_workspace / "crops")
    region_type, conf = segmenter._classify_region_content(gray, img_np)

    assert region_type == RegionType.ANSWER_TEXT


def test_classify_genuine_diagram(temp_workspace: Path) -> None:
    """Test D: Genuine drawn diagram with boxes and arrows is classified as DIAGRAM."""
    img = Image.new("RGB", (600, 400), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    # Box 1: Client
    draw.rectangle([50, 100, 200, 250], outline=(0, 0, 0), width=3)
    draw.text((90, 160), "Client", fill=(0, 0, 0))

    # Box 2: Server
    draw.rectangle([400, 100, 550, 250], outline=(0, 0, 0), width=3)
    draw.text((440, 160), "Server", fill=(0, 0, 0))

    # Connecting arrow / line
    draw.line([(200, 150), (400, 150)], fill=(0, 0, 0), width=3)
    draw.line([(385, 140), (400, 150), (385, 160)], fill=(0, 0, 0), width=3)
    draw.text((270, 130), "SYN", fill=(0, 0, 0))

    # Box 3: Router
    draw.rectangle([250, 280, 350, 360], outline=(0, 0, 0), width=3)
    draw.text((270, 310), "Router", fill=(0, 0, 0))

    img_np = np.array(img)
    gray = np.array(img.convert("L"))

    segmenter = QuestionSegmenter(crops_output_dir=temp_workspace / "crops")
    region_type, conf = segmenter._classify_region_content(gray, img_np)

    assert region_type == RegionType.DIAGRAM
    assert conf >= 0.70
