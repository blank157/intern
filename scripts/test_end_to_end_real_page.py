"""End-to-end live pipeline verification on the real student answer sheet with Qwen3-VL 4B."""

import asyncio
import sys
from pathlib import Path

# Add src to sys.path for local module resolution
src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from answer_eval.agents.ocr.agent import OCRAgent
from answer_eval.agents.reconstruction.service import ReconstructionService
from answer_eval.core.config import load_settings
from answer_eval.hardware.detector import detect_hardware
from answer_eval.inference.factory import create_inference_provider
from answer_eval.models.registry import get_model_registry
from answer_eval.processing.image.preprocessing import ImagePreprocessor
from answer_eval.processing.image.schemas import PreprocessingConfig
from answer_eval.processing.pdf.processor import PDFProcessor
from answer_eval.processing.segmentation.segmenter import QuestionSegmenter
from answer_eval.runtime.planner import RuntimePlanner

sys.stdout.reconfigure(encoding="utf-8")

async def main():
    print("=" * 70)
    print("LIVE END-TO-END VERIFICATION: SEGMENTATION + OCR + RECONSTRUCTION")
    print("=" * 70)

    # 1. Locate PDF
    pdf_files = list(Path("temp/test_ui").glob("**/*.pdf"))
    if not pdf_files:
        print("Error: No PDF found in temp/test_ui")
        return
    pdf_path = pdf_files[0]
    print(f"\n[1] Found PDF: {pdf_path}")

    session_dir = Path("temp/test_e2e_verification")
    session_dir.mkdir(parents=True, exist_ok=True)

    # 2. Render PDF
    print("\n[2] Rendering PDF at 300 DPI...")
    pdf_proc = PDFProcessor(default_dpi=300, output_dir=session_dir / "rendered")
    pdf_doc = pdf_proc.process_pdf(pdf_path, submission_id="SUB-LIVE-TEST", dpi=300)
    print(f"    Rendered {len(pdf_doc.pages)} pages.")

    # 3. Preprocess Page
    print("\n[3] Preprocessing page 1...")
    prep = ImagePreprocessor(
        config=PreprocessingConfig(
            deskew_enabled=True,
            border_removal_enabled=True,
            noise_reduction_enabled=True,
            contrast_adjustment_enabled=True,
        ),
        output_dir=session_dir / "preprocessed",
    )
    prep_page = prep.preprocess_page(pdf_doc.pages[0])
    print(f"    Preprocessed page: {prep_page.width_px}x{prep_page.height_px}")

    # 4. Question Segmentation
    print("\n[4] Segmenting page...")
    segmenter = QuestionSegmenter(crops_output_dir=session_dir / "crops")
    seg_res = segmenter.segment_page(prep_page, use_original_image=True)
    print(f"    Segmentation completed: {len(seg_res.regions)} regions found:")
    for reg in seg_res.regions:
        print(f"      - {reg.region_id}: type={reg.region_type.value}, conf={reg.classification_confidence:.2f}, bbox=[{reg.bbox.y_min:.3f}..{reg.bbox.y_max:.3f}]")

    # 5. Initialize Ollama Provider with Qwen3-VL 4B
    print("\n[5] Initializing Ollama provider with Qwen3-VL 4B...")
    reg = get_model_registry()
    settings = load_settings()
    profile = reg.get_profile("qwen3_vl_4b")
    provider = create_inference_provider(profile)
    planner = RuntimePlanner()
    hw = detect_hardware()
    rcfg = planner.plan_candidate(hw, profile, settings)
    await provider.initialize(profile, rcfg, hw)
    print("    Ollama provider initialized successfully.")

    # 6. OCR Extraction on ALL answer_text regions
    print(f"\n[6] Running Verbatim OCR on {len(seg_res.regions)} regions...")
    ocr_agent = OCRAgent(inference_provider=provider)
    ocr_results = []

    for idx, region in enumerate(seg_res.regions, 1):
        print(f"\n    --- Processing {region.region_id} ({idx}/{len(seg_res.regions)}) ---")
        ocr_res = await ocr_agent.extract_text(region)
        ocr_results.append((region, ocr_res))
        print(f"        Status: {ocr_res.status}")
        print(f"        Word count: {ocr_res.word_count}")
        print(f"        Transcription preview:\n        {repr(ocr_res.raw_text[:120])}")
        print(f"        Full text:\n{ocr_res.raw_text}")

    # 7. Answer Reconstruction
    print("\n[7] Reconstructing canonical structured answer...")
    recon = ReconstructionService()
    canonical = recon.reconstruct_answer(
        submission_id="SUB-LIVE-TEST",
        question_id="Q1",
        ocr_results=ocr_results,
        diagram_results=[],
    )

    print("\n" + "=" * 70)
    print("FINAL RECONSTRUCTED CANONICAL STRUCTURED ANSWER")
    print("=" * 70)
    print(f"Submission ID: {canonical.submission_id}")
    print(f"Question ID: {canonical.question_id}")
    print(f"Total word count: {canonical.word_count}")
    print(f"Total segments: {len(canonical.segments)}")
    print(f"Source pages: {canonical.source_pages}")
    print("\nCOMPLETE RAW VERBATIM TEXT:")
    print("-" * 50)
    print(canonical.raw_text)
    print("-" * 50)

    # 8. Shutdown
    await provider.shutdown()
    print("\nVerification completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
