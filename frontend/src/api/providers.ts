import { api } from "./client";
import type { ConnectivityResult, ModelSummary, ProviderSummary } from "./types";

export interface ProviderCreatePayload {
  name: string;
  type: string;
  base_url?: string;
  api_key?: string | null;
  enabled?: boolean;
}

export interface ProviderUpdatePayload {
  name?: string;
  type?: string;
  base_url?: string;
  api_key?: string | null;
  enabled?: boolean;
}

export interface ModelCreatePayload {
  name: string;
  supports_vision?: boolean;
  supports_streaming?: boolean;
  context_window?: number;
  is_default?: boolean;
  enabled?: boolean;
}

export const providersApi = {
  types: () => api.get<string[]>("/providers/types"),
  list: () => api.get<ProviderSummary[]>("/providers"),
  create: (payload: ProviderCreatePayload) =>
    api.post<ProviderSummary>("/providers", payload),
  update: (id: number, payload: ProviderUpdatePayload) =>
    api.patch<ProviderSummary>(`/providers/${id}`, payload),
  remove: (id: number) => api.delete<void>(`/providers/${id}`),
  probe: (id: number) =>
    api.post<ConnectivityResult>(`/providers/${id}/probe`),
  addModel: (providerId: number, payload: ModelCreatePayload) =>
    api.post<ModelSummary>(`/providers/${providerId}/models`, payload),
  removeModel: (providerId: number, modelId: number) =>
    api.delete<void>(`/providers/${providerId}/models/${modelId}`),
};
