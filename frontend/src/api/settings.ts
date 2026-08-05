import { api } from "./client";

export type Theme = "light" | "dark" | "system";
export type Difficulty = "easy" | "medium" | "hard";
export type QType = "concept" | "scenario";

export interface AppSettings {
  practice_default_limit: number;
  practice_time_limit_per_question: number | null;
  practice_default_difficulties: Difficulty[];
  practice_default_qtypes: QType[];
  practice_history_keep_n: number;
  appearance_theme: Theme;
  appearance_locale: string;
  timezone: string;
  llm_fallback_model_id: number | null;
}

export interface AppSettingsUpdate {
  practice_default_limit?: number;
  practice_time_limit_per_question?: number;
  practice_default_difficulties?: Difficulty[];
  practice_default_qtypes?: QType[];
  practice_history_keep_n?: number;
  appearance_theme?: Theme;
  appearance_locale?: string;
  timezone?: string;
  llm_fallback_model_id?: number | null;
  clear_llm_fallback_model?: boolean;
  /** When true, server clears the time limit (sets it to null). */
  clear_time_limit?: boolean;
}

export const settingsApi = {
  get: () => api.get<AppSettings>("/settings"),
  update: (payload: AppSettingsUpdate) =>
    api.put<AppSettings>("/settings", payload),
};
