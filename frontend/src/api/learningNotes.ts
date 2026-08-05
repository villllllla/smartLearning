import { api } from "./client";

export type ReviewFrequency = "daily" | "weekdays" | "weekly";

export interface NoteTag {
  id: number;
  name: string;
}

export interface LearningNoteSummary {
  id: number;
  title: string;
  summary: string;
  key_points: string[];
  category: string | null;
  quality_score: number | null;
  mastered: boolean;
  review_count: number;
  interval_index: number;
  next_review_at: string | null;
  last_reviewed_at: string | null;
  channel: string | null;
  created_at: string;
  updated_at: string;
  tags: NoteTag[];
}

export interface LearningNoteDetail extends LearningNoteSummary {
  raw_input: string;
  review: {
    issues?: string[];
    corrections?: string[];
    suggestions?: string[];
  };
  structured: Record<string, unknown>;
}

export interface LearningNoteListResponse {
  items: LearningNoteSummary[];
  total: number;
  due_today: number;
}

export interface LearningNoteCreate {
  raw_input: string;
  extra_tags?: string[];
}

export interface LearningNoteUpdate {
  title?: string;
  summary?: string;
  key_points?: string[];
  category?: string;
  tags?: string[];
  mastered?: boolean;
}

export interface ReviewSchedule {
  enabled: boolean;
  timezone: string;
  push_times: string[];
  frequency: ReviewFrequency;
  weekdays: number[];
  intervals_days: number[];
  max_notes_per_push: number;
  mastered_factor: number;
  recall_mode: boolean;
  feishu_enabled: boolean;
  last_run_slot: string | null;
  last_run_at: string | null;
  last_error: string | null;
}

export interface ReviewScheduleUpdate {
  enabled?: boolean;
  timezone?: string;
  push_times?: string[];
  frequency?: ReviewFrequency;
  weekdays?: number[];
  intervals_days?: number[];
  max_notes_per_push?: number;
  mastered_factor?: number;
  recall_mode?: boolean;
  feishu_enabled?: boolean;
}

export interface ReviewTriggerResult {
  ok: boolean;
  message: string;
  note_count: number;
  recipient_count: number;
}

function query(params: Record<string, string | number | boolean | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

export const learningNotesApi = {
  list: (params: {
    only_due?: boolean;
    include_mastered?: boolean;
    tag_id?: number;
    limit?: number;
    offset?: number;
  } = {}) =>
    api.get<LearningNoteListResponse>(`/learning-notes${query(params)}`),
  get: (id: number) => api.get<LearningNoteDetail>(`/learning-notes/${id}`),
  create: (body: LearningNoteCreate) =>
    api.post<LearningNoteDetail>("/learning-notes", body),
  update: (id: number, body: LearningNoteUpdate) =>
    api.patch<LearningNoteDetail>(`/learning-notes/${id}`, body),
  remove: (id: number) => api.delete<void>(`/learning-notes/${id}`),
  markReviewed: (id: number) =>
    api.post<LearningNoteDetail>(`/learning-notes/${id}/reviewed`),
  setMastered: (id: number, mastered: boolean) =>
    api.post<LearningNoteDetail>(
      `/learning-notes/${id}/master${query({ mastered })}`,
    ),
};

export const reviewScheduleApi = {
  get: () => api.get<ReviewSchedule>("/learning-review"),
  update: (body: ReviewScheduleUpdate) =>
    api.put<ReviewSchedule>("/learning-review", body),
  trigger: () => api.post<ReviewTriggerResult>("/learning-review/trigger"),
};
