import { api } from "./client";

export interface TodoSummary {
  id: number;
  title: string;
  description: string | null;
  status: string;
  progress: number;
  remind_at: string | null;
  timezone: string;
  reminded_at: string | null;
  completed_at: string | null;
  plan_id: number | null;
  long_term_id: number | null;
  plan_date: string | null;
  original_plan_date: string | null;
  defer_count: number;
  snooze_until: string | null;
  snooze_note: string | null;
  channel: string | null;
  clarification_question: string | null;
  created_at: string;
  updated_at: string;
}

export interface TodoDetail extends TodoSummary {
  raw_input: string;
  structured: Record<string, unknown>;
  clarification_context: { role: string; content: string }[];
}

export interface TodoListResponse {
  items: TodoSummary[];
  total: number;
}

export interface TodoCalendarDay {
  date: string;
  total: number;
  done: number;
}

export interface TodoCalendarResponse {
  days: TodoCalendarDay[];
  start: string;
  end: string;
}

export interface TodoCheckSchedule {
  enabled: boolean;
  timezone: string;
  check_time: string;
  push_today_plan: boolean;
  feishu_enabled: boolean;
  last_run_at: string | null;
  last_error: string | null;
}

export interface TodoCheckUpdate {
  enabled?: boolean;
  timezone?: string;
  check_time?: string;
  push_today_plan?: boolean;
  feishu_enabled?: boolean;
}

export interface TodoCheckTriggerResult {
  message: string;
  recipients: number;
}

function query(params: Record<string, string | number | boolean | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

export interface TodoDirectCreate {
  title: string;
  plan_date: string;
  remind_time?: string | null;
  description?: string | null;
}

export const todosApi = {
  list: (params: { status?: string; day?: string; plan_id?: number } = {}) =>
    api.get<TodoListResponse>(`/todos${query(params)}`),
  calendar: (start: string, end: string) =>
    api.get<TodoCalendarResponse>(`/todos/calendar${query({ start, end })}`),
  create: (body: TodoDirectCreate) => api.post<TodoDetail>("/todos", body),
  parse: (raw_input: string) => api.post<TodoDetail>("/todos/parse", { raw_input }),
  get: (id: number) => api.get<TodoDetail>(`/todos/${id}`),
  done: (id: number) => api.post<TodoDetail>(`/todos/${id}/done`),
  setProgress: (id: number, progress: number) =>
    api.post<TodoDetail>(`/todos/${id}/progress`, { progress }),
  cancel: (id: number) => api.post<TodoDetail>(`/todos/${id}/cancel`),
  restore: (id: number) => api.post<TodoDetail>(`/todos/${id}/restore`),
  remove: (id: number) => api.delete(`/todos/${id}`),
  snooze: (id: number, until: string, note?: string) =>
    api.post<TodoDetail>(`/todos/${id}/snooze`, { until, note: note ?? null }),
  unsnooze: (id: number) => api.post<TodoDetail>(`/todos/${id}/unsnooze`),
  update: (id: number, body: TodoDirectCreate & { description?: string | null }) =>
    api.put<TodoDetail>(`/todos/${id}`, body),
  getCheck: () => api.get<TodoCheckSchedule>("/todos/check"),
  updateCheck: (body: TodoCheckUpdate) =>
    api.put<TodoCheckSchedule>("/todos/check", body),
  triggerCheck: () => api.post<TodoCheckTriggerResult>("/todos/check/trigger"),
};
