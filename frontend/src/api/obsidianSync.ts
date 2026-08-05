import { api } from "./client";

export interface ObsidianSyncStatus {
  enabled: boolean;
  vault_path: string;
  vault_exists: boolean;
  debounce_seconds: number;
  dedupe_after_sync: boolean;
  mapped_files: number;
  last_full_scan_at: string | null;
  last_file_sync_at: string | null;
  recent_events: string[];
}

export interface ObsidianSyncRunResult {
  scanned: number;
  created: number;
  updated: number;
  skipped: number;
  failed: number;
  wikis_deduped?: number;
  wikis_repaired?: number;
  errors: string[];
}

export const obsidianSyncApi = {
  status: () => api.get<ObsidianSyncStatus>("/sync/obsidian/status"),
  scan: (force = false) =>
    api.post<ObsidianSyncRunResult>("/sync/obsidian/scan", { force }),
};
