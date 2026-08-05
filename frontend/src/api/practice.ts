import { api } from "./client";
import type { Difficulty, Grade, QType, QuestionSourceKind, QuestionSummary } from "./bank";

export interface PracticeSetupRequest {
  collection_id?: number | null;
  source_wiki_ids?: number[];
  tag_ids?: number[];
  tag_mode?: "and" | "or";
  difficulties?: Difficulty[];
  qtypes?: QType[];
  source_kinds?: QuestionSourceKind[];
  mode?: "sequential" | "random" | "wrong";
  limit?: number;
  time_limit_per_question?: number | null;
}

export interface PracticeSetupResponse {
  questions: QuestionSummary[];
  time_limit_per_question: number | null;
  total_pool: number;
}

export interface PracticeAnswerRequest {
  question_id: number;
  user_answer_text: string;
  override_model_id?: number | null;
}

export interface PracticeAnswerResponse {
  attempt_id: number;
  question_id: number;
  grade: Grade;
  score_correctness: number;
  score_completeness: number;
  score_structure: number;
  score_depth: number;
  feedback_text: string;
}

export const practiceApi = {
  setup: (body: PracticeSetupRequest) =>
    api.post<PracticeSetupResponse>("/practice/setup", body),
  answer: (body: PracticeAnswerRequest) =>
    api.post<PracticeAnswerResponse>("/practice/answer", body),
};
