import { api } from "./client";

export interface RagStatus {
  enabled: boolean;
  embedding_model: string;
  chunk_count: number;
  wiki_count_indexed: number;
  top_k: number;
  min_score: number;
  chunk_max_chars: number;
}

export interface RagSource {
  wiki_id: number;
  wiki_title: string;
  heading: string | null;
  chunk_index: number;
  score: number;
  url_path: string;
  excerpt: string;
}

export interface RagRebuildResult {
  wikis_processed: number;
  chunks_written: number;
  wikis_skipped: number;
  errors: string[];
}

export interface RagChunk {
  id: number;
  wiki_id: number;
  wiki_title: string;
  chunk_index: number;
  heading: string | null;
  text: string;
  source_commit_id: number | null;
  content_hash: string;
  text_length: number;
  created_at: string | null;
}

export interface RagChunkPage {
  items: RagChunk[];
  total: number;
  limit: number;
  offset: number;
}

export const ragApi = {
  status: () => api.get<RagStatus>("/rag/status"),
  rebuild: (wikiId?: number) =>
    api.post<RagRebuildResult>("/rag/rebuild", wikiId != null ? { wiki_id: wikiId } : {}),
  query: (query: string, topK?: number) =>
    api.post<{ hits: RagSource[] }>("/rag/query", { query, top_k: topK }),
  listChunks: (params: {
    wiki_id?: number;
    q?: string;
    limit?: number;
    offset?: number;
  } = {}) => {
    const search = new URLSearchParams();
    if (params.wiki_id != null) search.set("wiki_id", String(params.wiki_id));
    if (params.q) search.set("q", params.q);
    search.set("limit", String(params.limit ?? 30));
    search.set("offset", String(params.offset ?? 0));
    return api.get<RagChunkPage>(`/rag/chunks?${search.toString()}`);
  },
};
