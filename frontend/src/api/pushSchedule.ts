import { api } from "./client";
import type { Difficulty, QType } from "./settings";

export type PushFrequency = "daily" | "weekdays" | "weekly";
export type PushMode = "random" | "sequential" | "wrong";

export interface PushSchedule {
  enabled: boolean;
  timezone: string;
  push_times: string[];
  frequency: PushFrequency;
  weekdays: number[];
  limit: number;
  mode: PushMode;
  difficulties: Difficulty[];
  qtypes: QType[];
  tag_ids: number[];
  tag_mode: "and" | "or";
  source_kinds: ("simulated" | "interview")[];
  feishu_enabled: boolean;
  last_run_slot: string | null;
  last_run_at: string | null;
  last_error: string | null;
}

export interface PushScheduleUpdate {
  enabled?: boolean;
  timezone?: string;
  push_times?: string[];
  frequency?: PushFrequency;
  weekdays?: number[];
  limit?: number;
  mode?: PushMode;
  difficulties?: Difficulty[];
  qtypes?: QType[];
  tag_ids?: number[];
  tag_mode?: "and" | "or";
  source_kinds?: ("simulated" | "interview")[];
  feishu_enabled?: boolean;
}

export interface PushTriggerResult {
  ok: boolean;
  message: string;
  question_count: number;
  recipient_count: number;
}

export const pushScheduleApi = {
  get: () => api.get<PushSchedule>("/push-schedule"),
  update: (body: PushScheduleUpdate) => api.put<PushSchedule>("/push-schedule", body),
  trigger: () => api.post<PushTriggerResult>("/push-schedule/trigger"),
};
