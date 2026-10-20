import { useSyncExternalStore, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronDown, ChevronUp, Loader2, X } from "lucide-react";

import type { BulkGenerateItemResult } from "@/api/generation";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  getBulkGenerateState,
  hideBulkGenerateBar,
  showBulkGenerateBar,
  subscribeBulkGenerate,
} from "@/lib/bulkGenerateTask";

function useBulkGenerateTask() {
  return useSyncExternalStore(
    subscribeBulkGenerate,
    getBulkGenerateState,
    getBulkGenerateState,
  );
}

export function BulkGenerateProgressBar() {
  const task = useBulkGenerateTask();
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);

  if (!task.active) return null;

  if (!task.visible) {
    if (task.status !== "running") return null;
    return (
      <button
        type="button"
        onClick={showBulkGenerateBar}
        className={cn(
          "fixed z-[45] flex items-center gap-2 rounded-full border bg-card px-3 py-2 text-xs font-medium shadow-lg",
          // Clears the mobile tab bar, which grows by the gesture-bar inset
          // when the app runs installed (standalone) rather than in a tab.
          "bottom-[calc(5rem+env(safe-area-inset-bottom))] right-3 md:bottom-4 md:right-4",
        )}
      >
        <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
        生成中 {task.completedWikis}/{task.totalWikis}
        {task.pendingWikiCount > 0 ? ` · 排队${task.pendingWikiCount}` : ""}
      </button>
    );
  }

  const pct =
    task.totalWikis > 0
      ? Math.round((task.completedWikis / task.totalWikis) * 100)
      : 0;
  const running = task.status === "running";

  return (
    <div
      className={cn(
        "fixed z-[45] border-t bg-card/95 shadow-lg backdrop-blur supports-[backdrop-filter]:bg-card/90",
        "inset-x-0 bottom-[calc(4rem+env(safe-area-inset-bottom))] md:bottom-0 md:left-56",
      )}
      role="status"
      aria-live="polite"
    >
      <div className="mx-auto max-w-3xl px-3 py-2 md:px-6 md:py-3">
        <div className="flex items-start gap-3">
          {running && (
            <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-primary" />
          )}
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-sm font-medium">
              <span>
                {running
                  ? "批量生成进行中（可关闭窗口继续浏览）"
                  : task.status === "done"
                    ? "批量生成已完成"
                    : "批量生成失败"}
              </span>
              {running && (
                <span className="text-xs font-normal text-muted-foreground">
                  {task.completedWikis}/{task.totalWikis} 篇
                  {task.pendingWikiCount > 0
                    ? ` · 排队 ${task.pendingWikiCount} 篇`
                    : ""}
                  {task.totalBatches > 1
                    ? ` · 第 ${task.currentBatch}/${task.totalBatches} 批`
                    : ""}
                </span>
              )}
              {task.status === "done" && (
                <span className="text-xs font-normal text-muted-foreground">
                  成功 {task.successCount}
                  {task.failCount > 0 ? ` · 失败 ${task.failCount}` : ""}
                </span>
              )}
            </div>
            {running && task.currentTitle && (
              <p className="mt-0.5 truncate text-xs text-muted-foreground">
                当前：{task.currentTitle}
              </p>
            )}
            {task.status === "error" && task.error && (
              <p className="mt-0.5 text-xs text-destructive">{task.error}</p>
            )}
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
              <div
                className={cn(
                  "h-full rounded-full transition-all duration-300",
                  task.status === "error" ? "bg-destructive" : "bg-primary",
                )}
                style={{ width: `${task.status === "done" ? 100 : pct}%` }}
              />
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {(task.status === "done" || task.results.length > 0) && (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                aria-label={expanded ? "收起详情" : "展开详情"}
                onClick={() => setExpanded((v) => !v)}
              >
                {expanded ? (
                  <ChevronDown className="h-4 w-4" />
                ) : (
                  <ChevronUp className="h-4 w-4" />
                )}
              </Button>
            )}
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              aria-label={running ? "隐藏进度条" : "关闭"}
              onClick={() => {
                if (running) hideBulkGenerateBar();
                else hideBulkGenerateBar();
              }}
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {expanded && task.results.length > 0 && (
          <ResultList
            results={task.results}
            onOpenBatch={(batchId) => {
              hideBulkGenerateBar();
              navigate(`/bank/candidates/${batchId}`);
            }}
          />
        )}

        {task.status === "done" && !expanded && (
          <div className="mt-2 flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 text-xs"
              onClick={() => setExpanded(true)}
            >
              查看各篇结果
            </Button>
            {task.failCount > 0 && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 text-xs"
                onClick={showBulkGenerateBar}
              >
                重新展开
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function ResultList({
  results,
  onOpenBatch,
}: {
  results: BulkGenerateItemResult[];
  onOpenBatch: (batchId: string) => void;
}) {
  return (
    <ul className="mt-2 max-h-36 space-y-1 overflow-y-auto rounded-md border bg-muted/30 p-2 text-xs">
      {results.map((r) => (
        <li key={r.wiki_id} className="flex items-center justify-between gap-2">
          <span className="truncate">{r.wiki_title}</span>
          {r.success ? (
            <button
              type="button"
              className="shrink-0 text-primary hover:underline"
              onClick={() => r.batch_id && onOpenBatch(r.batch_id)}
            >
              {r.raw_count} 道 →
            </button>
          ) : (
            <span
              className="max-w-[45%] shrink-0 truncate text-destructive"
              title={r.error ?? ""}
            >
              {r.error ? `失败：${r.error}` : "失败"}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

/** Extra bottom padding when the progress bar is visible. */
export function useBulkGenerateLayoutPad(): string {
  const task = useBulkGenerateTask();
  if (!task.active || !task.visible) return "";
  return "pb-[calc(9rem+env(safe-area-inset-bottom))] md:pb-28";
}
