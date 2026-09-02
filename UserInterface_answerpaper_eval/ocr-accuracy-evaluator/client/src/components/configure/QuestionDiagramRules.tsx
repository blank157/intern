/** STYLE: EvalAI diagram rules — teacher-readable range and individual controls express visual-answer expectations without implying image analysis. */
import { ImageIcon, Info, ListChecks, Plus, Rows3, Trash2 } from "lucide-react";
import type { DiagramRuleMode, DiagramRuleRange, QuestionDiagramRule } from "./types";

interface QuestionDiagramRulesProps {
  mode: DiagramRuleMode;
  onModeChange: (mode: Exclude<DiagramRuleMode, null>) => void;
  ranges: DiagramRuleRange[];
  draft: Omit<DiagramRuleRange, "id">;
  onDraftChange: (draft: Omit<DiagramRuleRange, "id">) => void;
  onAddRange: () => void;
  onRemoveRange: (id: string) => void;
  questions: QuestionDiagramRule[];
  onQuestionChange: (question: number, update: Partial<Omit<QuestionDiagramRule, "question">>) => void;
}

export function QuestionDiagramRules({ mode, onModeChange, ranges, draft, onDraftChange, onAddRange, onRemoveRange, questions, onQuestionChange }: QuestionDiagramRulesProps) {
  const invalidRange = draft.to < draft.from;
  const overlapping = ranges.some((range) => draft.from <= range.to && draft.to >= range.from);
  const validDraft = !draft.required || (draft.minimumDiagrams >= 1 && draft.missingDiagramDeductions.length === draft.minimumDiagrams && draft.missingDiagramDeductions.every((value) => value >= 0.5));
  const setDraftCount = (count: number) => {
    const minimumDiagrams = Math.min(6, Math.max(1, Math.trunc(count)));
    onDraftChange({ ...draft, minimumDiagrams, missingDiagramDeductions: Array.from({ length: minimumDiagrams }, (_, index) => draft.missingDiagramDeductions[index] ?? 1) });
  };
  const setDraftDeduction = (index: number, value: number) => onDraftChange({ ...draft, missingDiagramDeductions: draft.missingDiagramDeductions.map((deduction, current) => current === index ? normalizeMark(value) : deduction) });

  return <div>
    <p className="type-overline text-[#7182ef]">Question diagram rules</p>
    <h3 className="mt-1 text-[15px] font-semibold tracking-[-0.022em] text-[#171827] dark:text-white">Where should diagrams be required?</h3>
    <p className="type-support mt-1.5 max-w-2xl text-slate-500 dark:text-slate-400">Optionally set diagram requirements by question range or individual question. These frontend-only rules describe your assessment expectation and do not imply automatic diagram analysis.</p>
    <div className="mt-4 grid gap-3 sm:grid-cols-2">
      <ModeCard active={mode === "ranges"} title="Question ranges" description="Apply the same diagram requirement across a selected question range." icon={Rows3} onClick={() => onModeChange("ranges")} />
      <ModeCard active={mode === "individual"} title="Individual questions" description="Choose diagram requirements separately for each question." icon={ListChecks} onClick={() => onModeChange("individual")} />
    </div>
    {mode === "ranges" && <div className="mt-5 rounded-2xl border border-[#e0e5ff] bg-[#f8f9ff]/75 p-4 dark:border-white/10 dark:bg-white/[0.035]">
      <p className="type-overline text-[#7182ef]">Diagram policy by question range</p>
      <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_1fr_1fr_auto]">
        <NumberField label="From question" value={draft.from} onChange={(from) => onDraftChange({ ...draft, from })} />
        <NumberField label="To question" value={draft.to} onChange={(to) => onDraftChange({ ...draft, to })} />
        <NumberField label="Minimum diagrams" value={draft.minimumDiagrams} max={6} onChange={setDraftCount} />
        <button type="button" onClick={onAddRange} disabled={invalidRange || overlapping || !validDraft} className="type-button self-end rounded-full bg-[#171b32] px-3.5 py-2.5 text-white disabled:cursor-not-allowed disabled:opacity-40 dark:bg-[#9aa8ff] dark:text-[#151827]"><Plus className="mr-1 inline h-3.5 w-3.5" />Add rule</button>
      </div>
      <DeductionFields count={draft.minimumDiagrams} deductions={draft.missingDiagramDeductions} onChange={setDraftDeduction} />
      {invalidRange && <RuleError>End question must be greater than or equal to the starting question.</RuleError>}
      {!invalidRange && overlapping && <RuleError>This range overlaps an existing diagram rule.</RuleError>}
      {ranges.length > 0 && <div className="mt-4 space-y-2">{ranges.map((range) => <RangeRow key={range.id} range={range} onRemove={() => onRemoveRange(range.id)} />)}</div>}
    </div>}
    {mode === "individual" && <div className="mt-5 rounded-2xl border border-[#e0e5ff] bg-[#f8f9ff]/75 p-4 dark:border-white/10 dark:bg-white/[0.035]">
      <div className="flex items-start gap-2"><ImageIcon className="mt-0.5 h-4 w-4 shrink-0 text-[#7182ef]" /><p className="text-[12px] font-semibold leading-5 text-slate-500 dark:text-slate-400">Set each question’s required diagram count and individual missing-diagram deduction. Leave a question as <strong className="text-slate-700 dark:text-white">No diagram required</strong> when a visual response is not expected.</p></div>
      <div className="mt-4 space-y-3">{questions.map((rule) => <IndividualRule key={rule.question} rule={rule} onChange={(update) => onQuestionChange(rule.question, update)} />)}</div>
    </div>}
  </div>;
}

function IndividualRule({ rule, onChange }: { rule: QuestionDiagramRule; onChange: (update: Partial<Omit<QuestionDiagramRule, "question">>) => void }) {
  const setCount = (count: number) => {
    const minimumDiagrams = Math.min(6, Math.max(1, Math.trunc(count)));
    onChange({ minimumDiagrams, missingDiagramDeductions: Array.from({ length: minimumDiagrams }, (_, index) => rule.missingDiagramDeductions[index] ?? 1) });
  };
  const setDeduction = (index: number, value: number) => onChange({ missingDiagramDeductions: rule.missingDiagramDeductions.map((deduction, current) => current === index ? normalizeMark(value) : deduction) });
  return <article className="rounded-xl border border-white/80 bg-white/80 p-3 dark:border-white/10 dark:bg-white/[0.04]"><div className="flex flex-wrap items-center justify-between gap-3"><p className="text-sm font-semibold text-[#171827] dark:text-white">Question {rule.question}</p><div className="flex rounded-full border border-[#dfe4ff] bg-[#f7f8ff] p-1 text-[10px] font-bold dark:border-white/10 dark:bg-white/[0.04]"><button type="button" onClick={() => onChange({ required: false })} className={`rounded-full px-2.5 py-1 transition-colors ${!rule.required ? "bg-white text-[#596dd8] shadow-sm dark:bg-white/10 dark:text-white" : "text-slate-500 dark:text-slate-400"}`}>No diagram</button><button type="button" onClick={() => onChange({ required: true, minimumDiagrams: Math.max(1, rule.minimumDiagrams), missingDiagramDeductions: rule.missingDiagramDeductions.length ? rule.missingDiagramDeductions : [1] })} className={`rounded-full px-2.5 py-1 transition-colors ${rule.required ? "bg-[#7182ef] text-white shadow-sm" : "text-slate-500 dark:text-slate-400"}`}>Required</button></div></div>
    {rule.required && <div className="mt-3 border-t border-[#edf0ff] pt-3 dark:border-white/[0.06]"><div className="grid gap-3 sm:grid-cols-[180px_1fr]"><NumberField label="Minimum diagrams" value={rule.minimumDiagrams} max={6} onChange={setCount} /><div className="grid gap-2 sm:grid-cols-2">{rule.missingDiagramDeductions.map((deduction, index) => <MarkField key={index} label={rule.minimumDiagrams === 1 ? "Required diagram missing" : `Diagram ${index + 1} missing`} value={deduction} onChange={(value) => setDeduction(index, value)} />)}</div></div></div>}
  </article>;
}

function DeductionFields({ count, deductions, onChange }: { count: number; deductions: number[]; onChange: (index: number, value: number) => void }) { return <div className="mt-4"><AnswerKeyNotice /><div className="mt-3 grid gap-3 sm:grid-cols-2">{Array.from({ length: count }, (_, index) => <MarkField key={index} label={count === 1 ? "Required diagram missing" : `Diagram ${index + 1} missing`} value={deductions[index] ?? 1} onChange={(value) => onChange(index, value)} />)}</div></div>; }
function RangeRow({ range, onRemove }: { range: DiagramRuleRange; onRemove: () => void }) { const detail = range.missingDiagramDeductions.map((deduction, index) => `D${index + 1}: ${deduction} ${deduction === 1 ? "mark" : "marks"}`).join(" · "); return <div className="flex items-center justify-between gap-3 rounded-xl border border-white/80 bg-white/75 px-3 py-2.5 text-sm dark:border-white/10 dark:bg-white/[0.04]"><div><p className="font-semibold text-[#171827] dark:text-white">Q{range.from} – Q{range.to} · {range.minimumDiagrams} {range.minimumDiagrams === 1 ? "diagram" : "diagrams"}</p><p className="mt-0.5 text-[11px] font-medium text-slate-500 dark:text-slate-400">{detail}</p></div><button type="button" onClick={onRemove} aria-label={`Remove diagram rule for questions ${range.from} to ${range.to}`} className="rounded-lg p-1.5 text-slate-400 hover:bg-[#fff1f0] hover:text-[#b85d59]"><Trash2 className="h-3.5 w-3.5" /></button></div>; }
function ModeCard({ active, title, description, icon: Icon, onClick }: { active: boolean; title: string; description: string; icon: typeof Rows3; onClick: () => void }) { return <button type="button" onClick={onClick} aria-pressed={active} className={`rounded-2xl border p-4 text-left transition-all focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#7788ff] ${active ? "border-[#7f90ef] bg-[#eef1ff]/85 shadow-[0_10px_24px_rgba(99,117,225,0.12)] dark:border-[#9aa8ff]/55 dark:bg-[#7587f2]/15" : "border-[#e0e5ff] bg-[#f8f9ff]/70 hover:border-[#bfc9ff] dark:border-white/10 dark:bg-white/[0.035]"}`}><Icon className={`h-5 w-5 ${active ? "text-[#6578e7] dark:text-[#b7c0ff]" : "text-slate-400"}`} /><p className="mt-3 text-sm font-extrabold text-[#171827] dark:text-white">{title}</p><p className="mt-1.5 text-xs font-medium leading-5 text-slate-500 dark:text-slate-400">{description}</p><span className={`mt-3 inline-flex rounded-full px-2.5 py-1 text-[11px] font-bold ${active ? "bg-[#6578e7] text-white" : "bg-white text-slate-500 dark:bg-white/5 dark:text-slate-300"}`}>{active ? "Selected" : "Select"}</span></button>; }
function NumberField({ label, value, max, onChange }: { label: string; value: number; max?: number; onChange: (value: number) => void }) { return <label className="text-[11px] font-bold text-slate-500 dark:text-slate-400">{label}<input min={1} max={max} type="number" value={value} onChange={(event) => onChange(Math.max(1, Math.min(max ?? Number.POSITIVE_INFINITY, Number(event.target.value))))} className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-semibold text-[#171827] outline-none focus:border-[#8292ee] dark:border-white/10 dark:bg-white/[0.04] dark:text-white" /></label>; }
function MarkField({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) { return <label className="rounded-xl border border-white/85 bg-white/80 p-3 text-[11px] font-semibold text-[#171827] shadow-sm dark:border-white/10 dark:bg-white/[0.04] dark:text-white">{label}<span className="mt-2 flex items-center gap-2"><input min={0.5} step={0.5} type="number" value={value} onChange={(event) => onChange(normalizeMark(Number(event.target.value)))} className="h-9 w-16 rounded-lg border border-[#dce2ff] bg-[#f8f9ff] px-2 text-center text-sm font-bold text-[#171827] outline-none focus:border-[#8292ee] dark:border-white/10 dark:bg-white/[0.06] dark:text-white" /><span className="text-[10px] font-medium text-slate-500 dark:text-slate-400">marks deducted</span></span></label>; }
function AnswerKeyNotice() { return <div className="mt-4 rounded-xl border border-[#fff0d5] bg-[#fff9ef] px-3 py-2.5"><p className="flex items-center gap-2 text-[11px] font-semibold leading-4 text-[#8e6321]"><Info className="h-3.5 w-3.5 shrink-0" />Diagram order is collected from the answer key. Diagram 1, Diagram 2, and later entries follow that answer-key order.</p></div>; }
function RuleError({ children }: { children: React.ReactNode }) { return <p className="mt-3 text-xs font-semibold text-[#b85d59]">{children}</p>; }
function normalizeMark(value: number) { return Math.max(0.5, Math.round(value * 2) / 2); }
