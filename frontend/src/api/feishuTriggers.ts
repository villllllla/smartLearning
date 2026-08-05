import { api } from "./client";

export type FeishuMatchMode = "prefix" | "exact";

export interface FeishuTriggerRule {
  id: number;
  action: string;
  title: string;
  description: string | null;
  match_mode: FeishuMatchMode;
  prefixes: string[];
  enabled: boolean;
  priority: number;
  is_system: boolean;
}

export interface FeishuTriggerRuleUpdate {
  action: string;
  prefixes?: string[];
  match_mode?: FeishuMatchMode;
  enabled?: boolean;
}

export interface FeishuTriggerListResponse {
  items: FeishuTriggerRule[];
}

export const feishuTriggersApi = {
  list: () => api.get<FeishuTriggerListResponse>("/feishu-triggers"),
  update: (items: FeishuTriggerRuleUpdate[]) =>
    api.put<FeishuTriggerListResponse>("/feishu-triggers", { items }),
  reset: () => api.post<FeishuTriggerListResponse>("/feishu-triggers/reset"),
};
