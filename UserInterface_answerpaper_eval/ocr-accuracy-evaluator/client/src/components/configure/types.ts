export type UploadStatus = "idle" | "uploading" | "complete";
export type StrictnessLevel = "lenient" | "moderate" | "strict";
export type StrictnessMode = "ranges" | "individual" | null;
export type WordCountMode = "ranges" | "individual" | null;
export type DiagramRuleMode = "ranges" | "individual" | null;

export interface UploadState {
  name: string | null;
  status: UploadStatus;
}

export interface StrictnessRange {
  id: string;
  from: number;
  to: number;
  level: StrictnessLevel;
}

export interface QuestionRule {
  question: number;
  level: StrictnessLevel;
}

export interface WordCountRange {
  id: string;
  from: number;
  to: number;
  minWords: number;
  shortfallWords: number;
  marksDeducted: number;
}

export interface QuestionWordCountRule {
  question: number;
  minWords: number;
  shortfallWords: number;
  marksDeducted: number;
}

export interface GlobalDiagramPolicy {
  required: boolean;
  minimumDiagrams: number;
  missingDiagramDeductions: number[];
}

export interface DiagramRuleRange {
  id: string;
  from: number;
  to: number;
  required: boolean;
  minimumDiagrams: number;
  missingDiagramDeductions: number[];
}

export interface QuestionDiagramRule {
  question: number;
  required: boolean;
  minimumDiagrams: number;
  missingDiagramDeductions: number[];
}

export const strictnessCopy: Record<StrictnessLevel, { title: string; description: string }> = {
  lenient: { title: "Lenient", description: "Accept equivalent wording and partial conceptual matches more generously." },
  moderate: { title: "Moderate", description: "Balance conceptual correctness, relevant detail, and reasonable wording differences." },
  strict: { title: "Strict", description: "Require close alignment with expected concepts, terminology, and required details." },
};
