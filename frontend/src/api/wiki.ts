import { api } from "./client";
import type { Page, UploadResponse, WikiDetail, WikiSummary } from "./types";

export interface BranchSummary {
  id: number;
  name: string;
  head_commit_id: number | null;
  created_at: string;
}

export interface BranchContent {
  branch: BranchSummary;
  head_commit_id: number | null;
  content_md: string;
  is_main: boolean;
}

export interface CommitSummary {
  id: number;
  branch_id: number;
  parent_commit_id: number | null;
  message: string;
  content_hash: string;
  created_at: string;
}

export type HunkKind = "clean" | "conflict";

export interface MergeHunk {
  id: number;
  kind: HunkKind;
  base_start: number;
  base_end: number;
  base_text: string;
  ours_text: string;
  theirs_text: string;
  resolved: string | null;
}

export interface MergePreview {
  source_branch_id: number;
  source_branch_name: string;
  target_branch_id: number;
  target_branch_name: string;
  base_commit_id: number | null;
  main_head_commit_id: number | null;
  source_head_commit_id: number | null;
  base_text: string;
  ours_text: string;
  theirs_text: string;
  hunks: MergeHunk[];
  auto_merged: string | null;
  has_conflict: boolean;
  conflict_count: number;
}

export const wikiApi = {
  list: (params: { q?: string; limit?: number; offset?: number } = {}) => {
    const search = new URLSearchParams();
    if (params.q) search.set("q", params.q);
    search.set("limit", String(params.limit ?? 20));
    search.set("offset", String(params.offset ?? 0));
    return api.get<Page<WikiSummary>>(`/wiki?${search.toString()}`);
  },
  get: (id: number) => api.get<WikiDetail>(`/wiki/${id}`),
  download: (id: number, branchId?: number | null) => {
    const q = branchId != null ? `?branch_id=${branchId}` : "";
    const today = new Date().toISOString().slice(0, 10).replace(/-/g, "");
    return api.download(`/wiki/${id}/download${q}`, `wiki-${id}-${today}.md`);
  },
  remove: (id: number) => api.delete<void>(`/wiki/${id}`),
  upload: (files: File[]) => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f, f.name);
    return api.upload<UploadResponse>("/wiki/upload", fd);
  },
};

export const branchApi = {
  list: (wikiId: number) => api.get<BranchSummary[]>(`/wiki/${wikiId}/branches`),
  get: (branchId: number) => api.get<BranchContent>(`/wiki/branches/${branchId}`),
  create: (wikiId: number, payload: { name: string; base_branch_id?: number }) =>
    api.post<BranchContent>(`/wiki/${wikiId}/branches`, payload),
  remove: (branchId: number) => api.delete<void>(`/wiki/branches/${branchId}`),
  commit: (
    branchId: number,
    payload: {
      content_md: string;
      message: string;
      expected_parent_commit_id: number | null;
    },
  ) => api.put<BranchContent>(`/wiki/branches/${branchId}/commit`, payload),
  commits: (branchId: number, limit = 50) =>
    api.get<CommitSummary[]>(`/wiki/branches/${branchId}/commits?limit=${limit}`),
  mergePreview: (branchId: number) =>
    api.get<MergePreview>(`/wiki/branches/${branchId}/merge-preview`),
  merge: (
    branchId: number,
    payload: {
      expected_main_head_id: number | null;
      message: string;
      resolutions?: Record<number, string> | null;
    },
  ) => api.post<BranchContent>(`/wiki/branches/${branchId}/merge`, payload),
};
