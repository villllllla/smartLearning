import { api } from "./client";
import type { Page } from "./types";

export interface BankCollectionSummary {
  id: number;
  name: string;
  parent_id: number | null;
  created_at: string;
}

export interface TagSummary {
  id: number;
  name: string;
}

export type Difficulty = "easy" | "medium" | "hard";
export type QType = "concept" | "scenario";
export type QuestionSourceKind = "simulated" | "interview";
export type Grade = "S" | "A" | "B" | "C";

export interface QuestionSummary {
  id: number;
  collection_id: number | null;
  question_text: string;
  answer_standard: string;
  difficulty: Difficulty;
  qtype: QType;
  source_kind: QuestionSourceKind;
  interview_answer_status: "pending" | "ready" | "failed" | null;
  source_wiki_id: number | null;
  source_wiki_title: string | null;
  source_commit_id: number | null;
  source_anchor: string | null;
  generated_by_prompt_id: number | null;
  generated_by_model_id: number | null;
  created_at: string;
  updated_at: string;
  tags: TagSummary[];
  last_grade: Grade | null;
  last_attempt_at: string | null;
  attempt_count: number;
}

export interface AttemptSummary {
  id: number;
  question_id: number;
  user_answer_text: string;
  grade: Grade;
  score_correctness: number;
  score_completeness: number;
  score_structure: number;
  score_depth: number;
  feedback_text: string;
  model_id: number | null;
  prompt_template_id: number | null;
  created_at: string;
}

export interface QuestionFilter {
  collection_id?: number;
  source_wiki_ids?: number[];
  tag_ids?: number[];
  tag_mode?: "and" | "or";
  difficulties?: Difficulty[];
  qtypes?: QType[];
  source_kinds?: QuestionSourceKind[];
  wrong_only?: boolean;
  q?: string;
  limit?: number;
  offset?: number;
}

function buildSearchParams(p: QuestionFilter): URLSearchParams {
  const sp = new URLSearchParams();
  if (p.collection_id !== undefined) sp.set("collection_id", String(p.collection_id));
  if (p.source_wiki_ids?.length)
    sp.set("source_wiki_ids", p.source_wiki_ids.join(","));
  if (p.tag_ids?.length) sp.set("tag_ids", p.tag_ids.join(","));
  if (p.tag_mode) sp.set("tag_mode", p.tag_mode);
  if (p.difficulties?.length) sp.set("difficulties", p.difficulties.join(","));
  if (p.qtypes?.length) sp.set("qtypes", p.qtypes.join(","));
  if (p.source_kinds?.length) sp.set("source_kinds", p.source_kinds.join(","));
  if (p.wrong_only) sp.set("wrong_only", "true");
  if (p.q) sp.set("q", p.q);
  sp.set("limit", String(p.limit ?? 20));
  sp.set("offset", String(p.offset ?? 0));
  return sp;
}

export const bankApi = {
  listCollections: () => api.get<BankCollectionSummary[]>("/bank/collections"),
  listTags: () => api.get<TagSummary[]>("/bank/tags"),
  listQuestions: (params: QuestionFilter = {}) =>
    api.get<Page<QuestionSummary>>(
      `/bank/questions?${buildSearchParams(params).toString()}`,
    ),
  getQuestion: (id: number) => api.get<QuestionSummary>(`/bank/questions/${id}`),
  listAttempts: (id: number, limit = 10) =>
    api.get<AttemptSummary[]>(`/bank/questions/${id}/attempts?limit=${limit}`),
  removeQuestion: (id: number) => api.delete<void>(`/bank/questions/${id}`),

  importInterviewNotes: (files: File[], collectionId?: number) => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    const q = collectionId != null ? `?collection_id=${collectionId}` : "";
    return api.upload<{
      parsed: number;
      imported: number;
      skipped_duplicates: number;
      doc_name: string;
      message: string;
      answer_job_id: string | null;
      answers_queued: number;
    }>(`/bank/import/interview-notes${q}`, fd);
  },

  getInterviewAnswerJob: (jobId: string) =>
    api.get<InterviewAnswerJob>(`/bank/interview-answer-jobs/${jobId}`),
  listInterviewAnswerJobs: () =>
    api.get<InterviewAnswerJob[]>("/bank/interview-answer-jobs"),
  backfillInterviewAnswers: () =>
    api.post<InterviewAnswerJob>("/bank/interview-answer-jobs/backfill"),

  dedupePreview: (params?: { threshold?: number; collection_id?: number }) => {
    const sp = new URLSearchParams();
    if (params?.threshold != null) sp.set("threshold", String(params.threshold));
    if (params?.collection_id != null)
      sp.set("collection_id", String(params.collection_id));
    const q = sp.toString();
    return api.get<DedupePreview>(`/bank/dedupe/preview${q ? `?${q}` : ""}`);
  },
  dedupeMerge: (body?: {
    threshold?: number;
    collection_id?: number;
    dry_run?: boolean;
  }) => api.post<DedupeMergeResult>("/bank/dedupe/merge", body ?? {}),
  dedupeBackfillEmbeddings: (collection_id?: number) => {
    const sp = new URLSearchParams();
    if (collection_id != null) sp.set("collection_id", String(collection_id));
    const q = sp.toString();
    return api.post<{ total_questions: number; newly_embedded: number }>(
      `/bank/dedupe/backfill-embeddings${q ? `?${q}` : ""}`,
    );
  },
};

export interface DedupeMember {
  id: number;
  question_text: string;
  attempt_count: number;
  similarity_to_canonical: number;
}

export interface DedupeCluster {
  canonical_id: number;
  canonical_text: string;
  members: DedupeMember[];
}

export interface DedupePreview {
  threshold: number;
  method: "string" | "embedding";
  total_questions: number;
  cluster_count: number;
  duplicate_question_count: number;
  clusters: DedupeCluster[];
}

export interface DedupeMergeResult {
  threshold: number;
  method: "string" | "embedding";
  dry_run: boolean;
  clusters_merged: number;
  questions_removed: number;
  attempts_reassigned: number;
}

export interface InterviewAnswerJob {
  job_id: string;
  doc_name: string;
  status: "queued" | "running" | "completed" | "failed";
  total: number;
  pack_count: number;
  completed_count: number;
  failed_count: number;
  cursor: number;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}
