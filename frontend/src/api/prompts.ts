import { api } from "./client";

export type Scene =
  | "chat_general"
  | "wiki_to_questions"
  | "answer_scoring"
  | "wiki_summary"
  | "learning_note_structuring"
  | "todo_intent_parsing"
  | "ai_news_curation"
  | "plan_decomposition"
  | "todo_motivation"
  | "interview_answer_generation";

export interface PromptTemplateSummary {
  id: number;
  name: string;
  scene: Scene;
  content: string;
  version_no: number;
  is_current: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface SceneInfo {
  scene: Scene;
  title: string;
  description: string;
  placeholders: string[];
  binding_model_id: number | null;
  binding_model_name: string | null;
  binding_provider_name: string | null;
  binding_fallback_model_id: number | null;
  binding_fallback_model_name: string | null;
  binding_fallback_provider_name: string | null;
  binding_params: Record<string, unknown>;
  binding_fallback_params: Record<string, unknown>;
  model_tier: "fast" | "capable" | string | null;
  model_hint: string | null;
  current_version_id: number | null;
  current_version_no: number | null;
  versions: PromptTemplateSummary[];
}

export interface CreateVersionRequest {
  scene: Scene;
  name: string;
  content: string;
  notes?: string | null;
  set_current?: boolean;
}

export interface UpdateBindingRequest {
  model_id?: number | null;
  fallback_model_id?: number | null;
  params?: Record<string, unknown> | null;
  fallback_params?: Record<string, unknown> | null;
}

export interface PreviewRenderRequest {
  content: string;
  variables: Record<string, string>;
}

export interface PreviewRenderResponse {
  rendered: string;
  missing_placeholders: string[];
  unused_variables: string[];
}

export const promptsApi = {
  listScenes: () => api.get<SceneInfo[]>("/prompts/scenes"),
  createVersion: (body: CreateVersionRequest) =>
    api.post<PromptTemplateSummary>("/prompts/versions", body),
  updateNotes: (versionId: number, notes: string | null) =>
    api.patch<PromptTemplateSummary>(`/prompts/versions/${versionId}`, { notes }),
  setCurrent: (versionId: number) =>
    api.post<{ scene: Scene; current_version_id: number }>(
      `/prompts/versions/${versionId}/set-current`,
      {},
    ),
  deleteVersion: (versionId: number) =>
    api.delete<void>(`/prompts/versions/${versionId}`),
  updateBinding: (scene: Scene, body: UpdateBindingRequest) =>
    api.patch<SceneInfo>(`/prompts/bindings/${scene}`, body),
  preview: (body: PreviewRenderRequest) =>
    api.post<PreviewRenderResponse>("/prompts/preview", body),
};
