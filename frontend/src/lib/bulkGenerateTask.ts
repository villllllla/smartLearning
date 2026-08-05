/**
 * In-browser background runner for bulk question generation.
 * Supports minimizing to bottom bar and enqueueing more wikis while running.
 */
import { ApiError } from "@/api/client";
import { generationApi, type BulkGenerateItemResult } from "@/api/generation";
import { toast } from "@/components/ui/toast";

export type BulkGenerateTaskStatus = "idle" | "running" | "done" | "error";

export interface BulkGenerateTaskState {
  active: boolean;
  visible: boolean;
  status: BulkGenerateTaskStatus;
  totalWikis: number;
  completedWikis: number;
  pendingWikiCount: number;
  queuedJobCount: number;
  currentBatch: number;
  totalBatches: number;
  currentTitle: string;
  results: BulkGenerateItemResult[];
  successCount: number;
  failCount: number;
  error: string | null;
}

export interface BulkGenerateStartParams {
  wiki_ids: number[];
  wiki_titles: Record<number, string>;
  n?: number | null;
  max_n?: number;
  replace_existing?: boolean;
}

type Listener = () => void;
const listeners = new Set<Listener>();

const initialState: BulkGenerateTaskState = {
  active: false,
  visible: false,
  status: "idle",
  totalWikis: 0,
  completedWikis: 0,
  pendingWikiCount: 0,
  queuedJobCount: 0,
  currentBatch: 0,
  totalBatches: 0,
  currentTitle: "",
  results: [],
  successCount: 0,
  failCount: 0,
  error: null,
};

let state: BulkGenerateTaskState = { ...initialState };
let draining = false;
const jobQueue: BulkGenerateStartParams[] = [];
const reservedWikiIds = new Set<number>();

function emit() {
  listeners.forEach((l) => l());
}

function patch(p: Partial<BulkGenerateTaskState>) {
  state = { ...state, ...p };
  emit();
}

function countPendingWikis(): number {
  return jobQueue.reduce((sum, job) => sum + job.wiki_ids.length, 0);
}

function syncQueueMeta() {
  patch({
    pendingWikiCount: countPendingWikis(),
    queuedJobCount: jobQueue.length,
  });
}

function recomputeResultCounts(results: BulkGenerateItemResult[]) {
  return {
    successCount: results.filter((r) => r.success).length,
    failCount: results.filter((r) => !r.success).length,
  };
}

export function getBulkGenerateState(): BulkGenerateTaskState {
  return state;
}

export function subscribeBulkGenerate(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function hideBulkGenerateBar() {
  if (state.status === "running" || draining) {
    patch({ visible: false });
    return;
  }
  jobQueue.length = 0;
  reservedWikiIds.clear();
  draining = false;
  state = { ...initialState };
  emit();
}

export function showBulkGenerateBar() {
  if (state.active) patch({ visible: true });
}

function filterNewWikiIds(ids: number[]): number[] {
  return ids.filter((id) => !reservedWikiIds.has(id));
}

function reserveWikiIds(ids: number[]) {
  for (const id of ids) reservedWikiIds.add(id);
}

function releaseWikiIds(ids: number[]) {
  for (const id of ids) reservedWikiIds.delete(id);
}

async function runOneJob(params: BulkGenerateStartParams): Promise<void> {
  const ids = params.wiki_ids;
  if (ids.length === 0) return;

  const completedBefore = state.completedWikis;
  const totalBatches = Math.max(1, Math.ceil(ids.length / 5));

  patch({
    status: "running",
    error: null,
    currentTitle: params.wiki_titles[ids[0]] ?? "",
    totalBatches,
    currentBatch: 0,
  });

  const merged = await generationApi.bulkGenerateForWikis(
    {
      wiki_ids: ids,
      n: params.n ?? null,
      max_n: params.max_n ?? 30,
      replace_existing: params.replace_existing ?? true,
    },
    {
      onBatchDone: ({ completedWikis, batchIndex, partial }) => {
        const chunkStart = (batchIndex - 1) * 5;
        const currentId = ids[chunkStart];
        const baseResults = state.results.filter((r) => !ids.includes(r.wiki_id));
        const jobResults = partial.results.filter((r) => ids.includes(r.wiki_id));
        const allResults = [...baseResults, ...jobResults];
        patch({
          currentBatch: batchIndex,
          currentTitle:
            (currentId != null ? params.wiki_titles[currentId] : "") ||
            `第 ${batchIndex} 批`,
          completedWikis: completedBefore + completedWikis,
          results: allResults,
          ...recomputeResultCounts(allResults),
        });
      },
    },
  );

  const baseResults = state.results.filter((r) => !ids.includes(r.wiki_id));
  const allResults = [...baseResults, ...merged.results];
  patch({
    completedWikis: completedBefore + ids.length,
    results: allResults,
    ...recomputeResultCounts(allResults),
  });

  if (merged.fail_count === 0 && ids.length === 1) {
    const ok = merged.results[0];
    if (ok?.success && ok.batch_id) {
      toast.success(
        `「${params.wiki_titles[ids[0]] ?? "文档"}」已生成 ${ok.raw_count ?? 0} 道候选题`,
      );
    }
  }

  releaseWikiIds(ids);
  syncQueueMeta();
}

async function drainQueue(opts?: { onDone?: () => void }): Promise<void> {
  if (draining) return;
  draining = true;

  try {
    while (jobQueue.length > 0) {
      const job = jobQueue.shift()!;
      syncQueueMeta();
      try {
        await runOneJob(job);
      } catch (e: unknown) {
        const msg =
          e instanceof ApiError
            ? e.message
            : e instanceof Error
              ? e.message
              : "未知错误";
        patch({ status: "error", error: msg });
        toast.error(`生成失败: ${msg}`);
        jobQueue.length = 0;
        syncQueueMeta();
        return;
      }
    }

    patch({
      status: "done",
      currentBatch: 0,
      currentTitle: "",
      pendingWikiCount: 0,
      queuedJobCount: 0,
    });

    const { successCount, failCount, totalWikis } = state;
    if (totalWikis > 1) {
      if (failCount === 0) {
        toast.success(`全部完成：${successCount} 篇`);
      } else {
        toast.info(`全部完成：成功 ${successCount} 篇，失败 ${failCount} 篇`);
      }
    }
    opts?.onDone?.();
  } finally {
    draining = false;
  }
}

export async function startBulkGenerate(
  params: BulkGenerateStartParams,
  opts?: { onDone?: () => void },
): Promise<void> {
  if (state.status === "done" || state.status === "error") {
    jobQueue.length = 0;
    reservedWikiIds.clear();
    draining = false;
    state = { ...initialState };
    emit();
  }

  const newIds = filterNewWikiIds(params.wiki_ids);
  if (newIds.length === 0) {
    toast.info("所选文档已在队列或正在生成中");
    showBulkGenerateBar();
    return;
  }

  const job: BulkGenerateStartParams = { ...params, wiki_ids: newIds };
  reserveWikiIds(newIds);

  const isAppend =
    draining || state.status === "running" || jobQueue.length > 0;

  if (isAppend) {
    jobQueue.push(job);
    patch({
      active: true,
      visible: true,
      totalWikis: state.totalWikis + newIds.length,
    });
    syncQueueMeta();
    toast.success(
      `已加入队列 ${newIds.length} 篇（共 ${state.totalWikis} 篇，含排队 ${state.pendingWikiCount} 篇）`,
    );
    showBulkGenerateBar();
    if (!draining) void drainQueue(opts);
    return;
  }

  jobQueue.length = 0;
  reservedWikiIds.clear();
  reserveWikiIds(newIds);

  patch({
    active: true,
    visible: true,
    status: "running",
    totalWikis: newIds.length,
    completedWikis: 0,
    pendingWikiCount: 0,
    queuedJobCount: 0,
    currentBatch: 0,
    totalBatches: Math.max(1, Math.ceil(newIds.length / 5)),
    currentTitle: params.wiki_titles[newIds[0]] ?? "",
    results: [],
    successCount: 0,
    failCount: 0,
    error: null,
  });

  jobQueue.push(job);
  void drainQueue(opts);
}

export function isBulkGenerateBusy(): boolean {
  return draining || state.status === "running" || jobQueue.length > 0;
}
