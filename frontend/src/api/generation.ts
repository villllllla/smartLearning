import { api } from "./client";
import type { CandidateBatchSummary } from "./types";

export interface CandidatePayload {
  question: string;
  answer: string;
  tag: string[];
  difficulty: "easy" | "medium" | "hard";
  type: "concept" | "scenario";
  origin?: string;
}

export interface CandidateSummary {
  id: number;
  batch_id: string;
  payload_json: CandidatePayload;
  picked: boolean;
  edited: boolean;
  source_wiki_id: number | null;
  source_commit_id: number | null;
  generated_by_prompt_id: number | null;
  generated_by_model_id: number | null;
  created_at: string;
}

export interface GenerateResponse {
  batch_id: string;
  raw_count: number;
  candidates: CandidateSummary[];
  replaced_bank_questions?: number;
  replaced_candidates?: number;
}

export interface BulkGenerateItemResult {
  wiki_id: number;
  wiki_title: string;
  success: boolean;
  batch_id?: string | null;
  raw_count?: number;
  replaced_bank_questions?: number;
  replaced_candidates?: number;
  error?: string | null;
}

export interface BulkGenerateResponse {
  results: BulkGenerateItemResult[];
  success_count: number;
  fail_count: number;
}

export interface CommitResponse {
  saved: number;
  remaining: number;
}

export interface BulkCommitItemResult {
  batch_id: string;
  saved: number;
  remaining: number;
}

export interface BulkCommitResponse {
  total_saved: number;
  total_remaining: number;
  batches_done: number;
  results: BulkCommitItemResult[];
}

export const generationApi = {
  /**
   * @param body.n     `null` / 缺省 → 自动模式(模型按内容决定题量,服务端会注入对应 directive)
   *                   number → 固定题数
   * @param body.max_n 自动模式的上限保护(默认 30) 同时也是固定模式的硬上限
   */
  generateForWiki: (
    wikiId: number,
    body: {
      n?: number | null;
      max_n?: number;
      model_id?: number | null;
      replace_existing?: boolean;
    } = {},
  ) =>
    api.post<GenerateResponse>(`/wiki/${wikiId}/generate-questions`, {
      n: body.n ?? null,
      max_n: body.max_n ?? 30,
      model_id: body.model_id ?? null,
      replace_existing: body.replace_existing ?? false,
    }),
  bulkGenerateForWikis: async (
    body: {
      wiki_ids: number[];
      n?: number | null;
      max_n?: number;
      model_id?: number | null;
      replace_existing?: boolean;
    },
    opts?: {
      /** Called after each 5-wiki HTTP batch completes. */
      onBatchDone?: (info: {
        completedWikis: number;
        totalWikis: number;
        batchIndex: number;
        batchTotal: number;
        partial: BulkGenerateResponse;
      }) => void;
    },
  ): Promise<BulkGenerateResponse> => {
    const payload = {
      n: body.n ?? null,
      max_n: body.max_n ?? 30,
      model_id: body.model_id ?? null,
      replace_existing: body.replace_existing ?? true,
    };
    const ids = body.wiki_ids;
    if (ids.length === 0) {
      return { results: [], success_count: 0, fail_count: 0 };
    }
    /** 每批最多 5 篇,减轻单次批量处理的注意力丢失。 */
    const CHUNK = 5;
    let merged: BulkGenerateResponse = {
      results: [],
      success_count: 0,
      fail_count: 0,
    };
    const batchTotal = Math.max(1, Math.ceil(ids.length / CHUNK));
    for (let i = 0; i < ids.length; i += CHUNK) {
      const chunk = ids.slice(i, i + CHUNK);
      const res = await api.post<BulkGenerateResponse>(
        "/wiki/bulk/generate-questions",
        { wiki_ids: chunk, ...payload },
      );
      merged = {
        results: [...merged.results, ...res.results],
        success_count: merged.success_count + res.success_count,
        fail_count: merged.fail_count + res.fail_count,
      };
      opts?.onBatchDone?.({
        completedWikis: Math.min(i + chunk.length, ids.length),
        totalWikis: ids.length,
        batchIndex: Math.floor(i / CHUNK) + 1,
        batchTotal,
        partial: merged,
      });
    }
    return merged;
  },
  listCandidateBatches: (limit = 100) =>
    api.get<CandidateBatchSummary[]>(`/candidates/batches?limit=${limit}`),
  listCandidates: (batchId: string) =>
    api.get<CandidateSummary[]>(`/candidates/${batchId}`),
  updateCandidate: (
    candId: number,
    body: { payload_json?: CandidatePayload; picked?: boolean },
  ) => api.patch<CandidateSummary>(`/candidates/${candId}`, body),
  discardCandidate: (candId: number) =>
    api.delete<void>(`/candidates/${candId}`),
  commitBatch: (
    batchId: string,
    body: { target_collection_id?: number; pick_all?: boolean } = {},
  ) => api.post<CommitResponse>(`/candidates/${batchId}/commit`, body),
  bulkCommitBatches: (body: {
    batch_ids: string[];
    pick_all?: boolean;
    target_collection_id?: number;
  }) => api.post<BulkCommitResponse>("/candidates/batches/bulk-commit", body),
};
