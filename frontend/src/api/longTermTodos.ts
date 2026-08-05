import { api } from "./client";

export type LongTermScheduleMode = "daily" | "weekdays";
export type LongTermStatus = "active" | "paused" | "done" | "archived";

export interface LongTermTodoSummary {
  id: number;
  title: string;
  description: string | null;
  start_date: string;
  end_date: string;
  remind_time: string;
  schedule_mode: LongTermScheduleMode;
  status: LongTermStatus;
  created_at: string;
  updated_at: string;
  done_count: number;
  total_count: number;
}

export interface LongTermTodoCreate {
  title: string;
  description?: string | null;
  start_date: string;
  end_date: string;
  remind_time?: string;
  schedule_mode?: LongTermScheduleMode;
}

export interface LongTermTodoUpdate {
  title?: string;
  description?: string | null;
  start_date?: string;
  end_date?: string;
  remind_time?: string;
  schedule_mode?: LongTermScheduleMode;
  status?: LongTermStatus;
}

export interface LongTermTodoListResponse {
  items: LongTermTodoSummary[];
  total: number;
}

export const longTermTodosApi = {
  list: () => api.get<LongTermTodoListResponse>("/long-term-todos"),
  get: (id: number) => api.get<LongTermTodoSummary>(`/long-term-todos/${id}`),
  create: (body: LongTermTodoCreate) =>
    api.post<LongTermTodoSummary>("/long-term-todos", body),
  update: (id: number, body: LongTermTodoUpdate) =>
    api.put<LongTermTodoSummary>(`/long-term-todos/${id}`, body),
  remove: (id: number) => api.delete<{ ok: boolean }>(`/long-term-todos/${id}`),
};
