/** STYLE: EvalAI key review — teacher validates the AI-parsed answer key before it becomes the locked grading source. */
import { AlertTriangle, CheckCircle2, ImageIcon, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import {
  fetchDiagramBlobUrl,
  reviewAnswerKey,
  type AnswerKeyPayload,
  type QuestionReviewEdit,
} from "@/api/answerKeys";

interface AnswerKeyReviewStepProps {
  payload: AnswerKeyPayload;
  onConfirmed: (payload: AnswerKeyPayload) => void;
  onReupload: () => void;
}

export function AnswerKeyReviewStep({ payload, onConfirmed, onReupload }: AnswerKeyReviewStepProps) {
  const [questions, setQuestions] = useState(payload.questions);
  const [saving, setSaving] = useState(false);
  const [diagramUrls, setDiagramUrls] = useState<Record<string, string>>({});

  useEffect(() => setQuestions(payload.questions), [payload]);
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const next: Record<string, string> = {};
      for (const question of payload.questions) {
        for (const diagram of question.diagrams) {
          try {
            next[diagram.id] = await fetchDiagramBlobUrl(payload.answer_key.id, diagram.id);
          } catch {
            /* image preview is best-effort */
          }
        }
      }
      if (!cancelled) setDiagramUrls(next);
    };
    void load();
    return () => {
      cancelled = true;
      Object.values(diagramUrls).forEach((url) => URL.revokeObjectURL(url));
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [payload]);

  const editQuestion = (questionNumber: number, patch: Partial<{ questionText: string; expected: string; maxMarks: number; keywords: string }>) => {
    setQuestions((current) => current.map((q) => (q.question_number === questionNumber ? { ...q, ...patchMap(patch, q) } : q)));
  };

  const confirm = async () => {
    setSaving(true);
    try {
      const edits: QuestionReviewEdit[] = questions.map((question) => ({
        question_number: question.question_number,
        question_text: typeof question.question_text === "string" ? question.question_text : undefined,
        expected_answer_text: question.expected_answer_text,
        maximum_marks: Number(question.maximum_marks),
        keywords: question.keywords,
        mandatory_terms: question.mandatory_terms,
      }));
      const result = await reviewAnswerKey(payload.answer_key.id, { edits, confirm: true });
      onConfirmed(result);
    } finally {
      setSaving(false);
    }
  };

  const warnings = payload.answer_key.parse_error ? [payload.answer_key.parse_error] : [];

  return <section className="space-y-4">
    <div className="rounded-[24px] border border-white/85 bg-white/70 p-5 shadow-[0_14px_34px_rgba(60,70,135,0.08)] backdrop-blur-xl dark:border-white/10 dark:bg-[#202334]/72 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="type-overline text-[#7182ef]">Answer key parsed</p>
          <h2 className="type-section-title mt-1.5 text-[#171827] dark:text-white">{questions.length} questions detected.</h2>
          <p className="type-support mt-2 text-slate-500 dark:text-slate-400">Check what the AI extracted — these details become the locked grading source. Correct anything before continuing.</p>
        </div>
        <button type="button" onClick={onReupload} className="type-button rounded-xl border border-[#dfe4ff] bg-white/80 px-3 py-2 text-[12px] font-bold text-[#5d6ee0] hover:border-[#7788ff]">Re-upload key</button>
      </div>
      {warnings.length > 0 && <div className="mt-4 flex items-start gap-2 rounded-2xl bg-[#fdf3e7] px-3.5 py-3 text-[12px] font-semibold text-[#a4691c]"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{warnings.join(" · ")}</div>}
    </div>

    <div className="space-y-3">
      {questions.map((question) => (
        <article key={question.id} className="rounded-[20px] border border-white/85 bg-white/72 p-4 shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-[#202334]/72">
          <header className="flex flex-wrap items-center gap-2">
            <span className="inline-flex h-7 min-w-7 items-center justify-center rounded-lg bg-[#171b32] px-1.5 text-[11px] font-extrabold text-white">Q{question.question_number}</span>
            <span className="rounded-full bg-[#eef1ff] px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-[#6679e8] dark:bg-white/10 dark:text-[#b2bcff]">{question.answer_type}</span>
            <span className="text-[11px] font-semibold text-slate-500">{question.concepts.length || "—"} concept rubric · {question.keywords.length} keywords</span>
          </header>
          <div className="mt-3 grid gap-3 lg:grid-cols-[1fr_240px]">
            <div className="space-y-2.5">
              <input value={String(question.question_text ?? "")} onChange={(event) => editQuestion(question.question_number, { questionText: event.target.value })} placeholder="Question text" className="w-full rounded-xl border border-[#dfe4ff] bg-white/85 px-3 py-2 text-[13px] font-semibold outline-none focus:border-[#7788ff]" />
              <textarea value={question.expected_answer_text} onChange={(event) => editQuestion(question.question_number, { expected: event.target.value })} rows={3} placeholder="Expected answer" className="w-full rounded-xl border border-[#dfe4ff] bg-white/85 px-3 py-2 text-[12px] leading-5 outline-none focus:border-[#7788ff]" />
              <div className="flex gap-2">
                <label className="flex items-center gap-1.5 text-[11px] font-bold text-slate-500">Max marks<input type="number" min={0} value={Number(question.maximum_marks)} onChange={(event) => editQuestion(question.question_number, { maxMarks: Number(event.target.value) })} className="w-20 rounded-lg border border-[#dfe4ff] bg-white/85 px-2 py-1.5 text-right text-[12px] font-bold outline-none focus:border-[#7788ff]" /></label>
                <input value={question.keywords.join(", ")} onChange={(event) => editQuestion(question.question_number, { keywords: event.target.value })} placeholder="keywords, comma separated" className="min-w-0 flex-1 rounded-lg border border-[#dfe4ff] bg-white/85 px-2.5 py-1.5 text-[12px] outline-none focus:border-[#7788ff]" />
              </div>
              {question.parser_uncertainties.length > 0 && <p className="flex items-start gap-1.5 text-[11px] font-semibold text-[#a4691c]"><AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />{question.parser_uncertainties.join(" · ")}</p>}
            </div>
            <div className="space-y-2">
              {question.math_rubric.length > 0 && <div className="rounded-xl bg-[#f4f6ff] p-2.5 text-[11px] font-semibold text-[#45509e] dark:bg-white/5 dark:text-[#b2bcff]">{question.math_rubric.map((step) => `${step.step_id}: ${step.description} (+${step.marks})`).join(" · ")}</div>}
              {question.diagrams.length > 0 && <div className="grid gap-2">{question.diagrams.map((diagram) => (
                <figure key={diagram.id} className="overflow-hidden rounded-xl border border-[#dfe4ff] bg-white/85 dark:border-white/10">
                  {diagramUrls[diagram.id]
                    ? <img src={diagramUrls[diagram.id]} alt={`${diagram.diagram_code} crop`} className="max-h-32 w-full object-contain" />
                    : <div className="flex h-20 items-center justify-center text-slate-300"><Loader2 className="h-4 w-4 animate-spin" /></div>}
                  <figcaption className="flex items-center gap-1 px-2 py-1 text-[10px] font-bold text-slate-500"><ImageIcon className="h-3 w-3" />{diagram.diagram_code}{diagram.type_label ? ` · ${diagram.type_label}` : ""}{diagram.parser_uncertain ? " · verify" : ""}</figcaption>
                </figure>
              ))}</div>}
              {question.answer_type === "numerical" && question.math_rubric.length === 0 && <p className="text-[11px] font-semibold text-[#a4691c]">No step-wise math marking detected.</p>}
            </div>
          </div>
        </article>
      ))}
    </div>

    <div className="flex justify-end">
      <button disabled={saving} onClick={confirm} className="type-button inline-flex items-center gap-2 rounded-2xl bg-[#7788ff] px-5 py-3 text-[13px] font-bold text-white shadow-[0_10px_24px_rgba(119,136,255,0.3)] disabled:opacity-70">{saving ? "Locking…" : "Confirm answer key"}<CheckCircle2 className="h-4 w-4" /></button>
    </div>
  </section>;
}

function patchMap(patch: { questionText?: string; expected?: string; maxMarks?: number; keywords?: string }, _original: AnswerKeyPayload["questions"][number]) {
  const mapped: Record<string, unknown> = {};
  if (patch.questionText !== undefined) mapped.question_text = patch.questionText;
  if (patch.expected !== undefined) mapped.expected_answer_text = patch.expected;
  if (patch.maxMarks !== undefined) mapped.maximum_marks = patch.maxMarks;
  if (patch.keywords !== undefined) mapped.keywords = patch.keywords.split(",").map((term) => term.trim()).filter(Boolean);
  return mapped;
}
