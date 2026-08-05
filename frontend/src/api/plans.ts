import { api } from "./client";

export interface PlanTaskDraft {
  date: string;
  title: string;
  description: string;
}

export interface PlanPreviewRequest {
  title: string;
  goal: string;
  start_date: string;
  end_date: string;
}

export interface PlanPreviewResponse {
  title: string;
  goal: string;
  start_date: string;
  end_date: string;
  tasks: PlanTaskDraft[];
  prompt_id: number | null;
  model_id: number | null;
}

export interface PlanCreateRequest {
  title: string;
  goal: string;
  start_date: string;
  end_date: string;
  tasks: PlanTaskDraft[];
  prompt_id?: number | null;
  model_id?: number | null;
}

export interface PlanSummary {
  id: number;
  title: string;
  goal: string | null;
  start_date: string;
  end_date: string;
  status: string;
  created_at: string;
  updated_at: string;
  done_count: number;
  total_count: number;
}

export interface PlanListResponse {
  items: PlanSummary[];
  total: number;
}

export const plansApi = {
  list: () => api.get<PlanListResponse>("/plans"),
  preview: (body: PlanPreviewRequest) =>
    api.post<PlanPreviewResponse>("/plans/preview", body),
  create: (body: PlanCreateRequest) => api.post<PlanSummary>("/plans", body),
  remove: (id: number) => api.delete<{ ok: boolean }>(`/plans/${id}`),
};
