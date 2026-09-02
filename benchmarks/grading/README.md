# Grading Benchmark Structure (Modules 12-16)

This directory is RESERVED for a real teacher-labelled grading dataset.

    questions/       answer-key / rubric JSON files (QuestionRubric schema)
    answers/         canonical student answers linked by question_id
    teacher_scores/  consensus scores from >= 2 human teachers

## STATUS: NO LABELLED DATA EXISTS YET

The synthetic fixtures in `tests/unit/test_grading_*.py` are UNIT TESTS ONLY.
They validate code paths with scripted model outputs — they are NOT evidence
of real-world grading accuracy.

Do NOT invent teacher consensus scores. The following metrics must not be
claimed until this dataset contains real double-marked answers:

- mean absolute mark difference vs teachers
- % of criteria within ±0.5 / ±1 mark
- weighted Cohen's kappa
- criterion-level agreement rate
- grader/verifier disagreement rate on real data
- human override rate
