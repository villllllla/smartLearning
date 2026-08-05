import type { QuestionSummary } from "@/api/bank";
import type { PracticeAnswerResponse } from "@/api/practice";

/** Per-tab in-memory practice session. Survives navigation but not refresh. */
export interface PracticeSession {
  questions: QuestionSummary[];
  answers: Record<number, { text: string; result: PracticeAnswerResponse }>;
  timeLimit: number | null;
  startedAt: number;
}

let _session: PracticeSession | null = null;

export function setPracticeSession(s: PracticeSession | null) {
  _session = s;
}

export function getPracticeSession(): PracticeSession | null {
  return _session;
}

export function recordAnswer(
  questionId: number,
  text: string,
  result: PracticeAnswerResponse,
) {
  if (!_session) return;
  _session.answers[questionId] = { text, result };
}
