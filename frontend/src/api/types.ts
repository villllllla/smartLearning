export interface WikiSummary {
  id: number;
  title: string;
  collection_id: number | null;
  /** null 表示尚无 main 正文，批量生成会失败 */
  current_main_commit_id?: number | null;
  word_count: number;
  excerpt: string | null;
  updated_at: string;
  created_at: string;
  /** 已入库且未删除的题目数 */
  bank_question_count?: number;
  /** 最新一批候选数（与预览页一致） */
  pending_candidate_count?: number;
  /** 该文档全部未入库候选总数 */
  pending_candidate_total?: number;
  pending_batch_count?: number;
  /** 最近一批未提交候选的 batch_id，用于跳转预览页 */
  pending_batch_id?: string | null;
}

export interface CandidateBatchSummary {
  batch_id: string;
  count: number;
  created_at: string;
  source_wiki_id: number | null;
  source_wiki_title: string | null;
}

export interface TocItem {
  level: number;
  text: string;
  anchor: string;
}

export interface BranchSummary {
  id: number;
  name: string;
  head_commit_id: number | null;
  created_at: string;
}

export interface WikiDetail extends WikiSummary {
  current_main_commit_id: number | null;
  content_md: string;
  toc: TocItem[];
  branches: BranchSummary[];
}

export interface UploadResultItem {
  filename: string;
  success: boolean;
  wiki_id?: number | null;
  title?: string | null;
  error?: string | null;
}

export interface UploadResponse {
  created: number;
  failed: number;
  results: UploadResultItem[];
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface ModelSummary {
  id: number;
  provider_id: number;
  name: string;
  supports_vision: boolean;
  supports_streaming: boolean;
  context_window: number;
  is_default: boolean;
  enabled: boolean;
  created_at: string;
}

export interface ProviderSummary {
  id: number;
  name: string;
  type: string;
  base_url: string;
  enabled: boolean;
  has_api_key: boolean;
  masked_api_key: string;
  created_at: string;
  models: ModelSummary[];
}

export interface ConnectivityResult {
  ok: boolean;
  elapsed_ms: number;
  detail: string;
  discovered_models: string[];
  chat_probe_ok?: boolean | null;
  chat_probe_elapsed_ms?: number | null;
  chat_probe_detail?: string;
  request_timeout_seconds?: number;
}
