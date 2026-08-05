import { api } from "./client";

export type NewsFrequency = "daily" | "weekdays" | "weekly";

export interface AiNewsItem {
  id: number;
  rank: number;
  title: string;
  original_title: string;
  url: string;
  source: string;
  summary: string;
  heat_score: number;
  why: string | null;
  raw_score: number;
  published_at: string | null;
}

export interface AiNewsDigest {
  id: number;
  run_slot: string | null;
  item_count: number;
  total_candidates: number;
  used_llm: boolean;
  channel: string | null;
  created_at: string;
  items: AiNewsItem[];
}

export interface AiNewsListResponse {
  items: AiNewsDigest[];
  total: number;
}

export interface RssFeed {
  name: string;
  url: string;
}

export interface AiNewsSchedule {
  enabled: boolean;
  timezone: string;
  push_times: string[];
  frequency: NewsFrequency;
  weekdays: number[];
  top_n: number;
  enable_hackernews: boolean;
  enable_github: boolean;
  enable_arxiv: boolean;
  enable_huggingface: boolean;
  enable_reddit: boolean;
  rss_feeds: RssFeed[];
  dedup_days: number;
  feishu_enabled: boolean;
  last_run_slot: string | null;
  last_run_at: string | null;
  last_error: string | null;
}

export interface AiNewsScheduleUpdate {
  enabled?: boolean;
  timezone?: string;
  push_times?: string[];
  frequency?: NewsFrequency;
  weekdays?: number[];
  top_n?: number;
  enable_hackernews?: boolean;
  enable_github?: boolean;
  enable_arxiv?: boolean;
  enable_huggingface?: boolean;
  enable_reddit?: boolean;
  rss_feeds?: RssFeed[];
  dedup_days?: number;
  feishu_enabled?: boolean;
}

export interface AiNewsTriggerResult {
  ok: boolean;
  message: string;
  item_count: number;
  recipient_count: number;
  digest_id: number | null;
}

function query(params: Record<string, string | number | boolean | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

export const aiNewsApi = {
  list: (params: { limit?: number; offset?: number } = {}) =>
    api.get<AiNewsListResponse>(`/ai-news${query(params)}`),
  getSchedule: () => api.get<AiNewsSchedule>("/ai-news/schedule"),
  updateSchedule: (body: AiNewsScheduleUpdate) =>
    api.put<AiNewsSchedule>("/ai-news/schedule", body),
  trigger: () => api.post<AiNewsTriggerResult>("/ai-news/trigger"),
};
