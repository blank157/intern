"""Live end-to-end grading verification: GradingService -> real qwen3-vl:4b via Ollama.

Runs Modules 12-16 for real (rules -> strictness -> evaluator -> blind verifier
-> comparator -> risk) against the live Ollama model, plus the empty-answer
deterministic shortcut (no model call). Run from project root:
  python scripts/test_grading_live.py
"""

import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from answer_eval.agents.reconstruction.schemas import AnswerSegment, CanonicalStructuredAnswer  # noqa: E402
from answer_eval.core.provenance import Provenance  # noqa: E402
from answer_eval.grading.rubric import ExpectedConcept, QuestionRubric  # noqa: E402
from answer_eval.grading.service import GradingService  # noqa: E402
from answer_eval.inference.ollama_provider import OllamaProvider  # noqa: E402

# Deliberately a SEMANTIC PARAPHRASE: covers both concepts without the literal
# keywords "acknowledgement"/"retransmission" — proves keywords are signals only.
STUDENT_ANSWER = (
    "TCP is a reliable transport protocol used on the internet. Before any data is "
    "exchanged, the sender and receiver perform a handshake that establishes a session "
    "between them, so communication only happens inside this established session. While "
    "data is being transferred, the receiving host returns a short confirmation message "
    "for every segment it successfully accepts. If the sending side does not receive this "
    "confirmation within a fixed timeout period, it assumes the segment was lost and "
    "transmits that segment again. Sequence numbers allow the receiver to reorder segments "
    "that arrive out of order and detect duplicates. Together these mechanisms guarantee "
    "that applications receive every byte exactly once and in the correct order."
)


def make_provenance() -> Provenance:
    return Provenance(
        submission_id="SUB-LIVE-GRADE",
        page_number=1,
        region_id="REG-1",
        question_id="Q4",
        source_image_hash="hash-q4",
        request_id="req-live-grade",
        model_id="qwen3-vl:4b",
    )


def make_answer(text: str) -> CanonicalStructuredAnswer:
    return CanonicalStructuredAnswer(
        submission_id="SUB-LIVE-GRADE",
        question_id="Q4",
        source_pages=[1],
        raw_text=text,
        word_count=len(text.split()),
        segments=[AnswerSegment(page_number=1, region_id="REG-1", reading_order=1, raw_text=text)],
        diagrams=[],
        flags=[],
        provenance=make_provenance(),
    )


def make_rubric() -> QuestionRubric:
    return QuestionRubric(
        question_id="Q4",
        question_text="Explain how TCP provides reliable communication.",
        maximum_marks=10,
        expected_concepts=[
            ExpectedConcept(
                concept_id="C1",
                description="Connection-oriented communication",
                maximum_marks=5,
            ),
            ExpectedConcept(
                concept_id="C2",
                description="Acknowledgement mechanism",
                maximum_marks=5,
            ),
        ],
        keywords=["acknowledgement", "retransmission"],
        mandatory_terms=["TCP"],
        minimum_words=100,
        strictness=60,
    )


def print_graded(graded, wall: float) -> None:
    m, c, r = graded.marks, graded.comparison, graded.risk
    print("=" * 70)
    print(f"[GRADED] Q4  ({wall:.1f}s total)")
    print("-" * 70)
    print(
        f"DETERMINISTIC FACTS : words={graded.rule_result.word_count.actual}"
        f" (min {graded.rule_result.word_count.minimum}, effective"
        f" {graded.rule_result.word_count.effective_minimum})"
        f"\n                      keywords matched={graded.rule_result.keywords.matched}"
        f" missing_optional={graded.rule_result.keywords.missing_optional}"
        f"\n                      mandatory missing={graded.rule_result.mandatory_terms.missing}"
        f" flags={graded.rule_result.flags}"
    )
    print(f"MARKS               : criteria_total={m.criteria_total} penalty={m.deterministic_penalty} "
          f"final={m.final_proposed_marks}/{m.maximum_marks}")
    print(f"COMPARISON          : evaluator={c.evaluator_total} verifier={c.verifier_total} "
          f"diff={c.total_difference} agreement={c.criterion_agreement_rate:.2f} major={c.major_disagreement}")
    print(f"RISK                : level={r.risk_level} auto_approve={r.auto_approve} reasons={r.review_reasons}")
    print(f"REVIEW              : required={graded.review.required} status={graded.review.status}")
    print("-" * 70)
    for crit in graded.evaluation.criteria:
        ev = "; ".join(repr(e.quote)[:60] for e in (crit.student_evidence or [])[:2]) or "(no evidence)"
        print(
            f"  [{crit.criterion_id}] {crit.status.value if hasattr(crit.status, 'value') else crit.status}"
            f" / {crit.match_type.value if hasattr(crit.match_type, 'value') else crit.match_type}"
            f"  {crit.proposed_marks}/{crit.maximum_marks}\n"
            f"      evidence: {ev}\n"
            f"      reason:   {crit.reason[:110]}"
        )
    print(f"FEEDBACK            : {graded.evaluation.feedback}")
    print(f"VERSIONS            : {graded.versions.model_dump()}")


async def main() -> None:
    provider = OllamaProvider(timeout_seconds=600.0)
    health = await provider.check_detailed_health()
    print(f"Health: available={health['available']} model={health['model']}")
    if not health["available"]:
        print(health.get("help_message"))
        return

    service = GradingService(inference_provider=provider)
    loop = asyncio.get_event_loop()

    # Case 1 — full semantic grading with the real model.
    t0 = loop.time()
    graded = await service.grade_question(make_answer(STUDENT_ANSWER), make_rubric())
    print_graded(graded, loop.time() - t0)

    # Case 2 — empty answer: deterministic shortcut, NO model call, routes to review.
    t0 = loop.time()
    graded_empty = await service.grade_question(make_answer(""), make_rubric())
    print("=" * 70)
    print(f"[EMPTY-ANSWER SHORTCUT] ({loop.time() - t0:.3f}s, no model call)")
    print(
        f"  final={graded_empty.marks.final_proposed_marks}/"
        f"{graded_empty.marks.maximum_marks}  risk={graded_empty.risk.risk_level}"
        f"  review_required={graded_empty.review.required}  flags={graded_empty.flags}"
    )

    await provider.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
