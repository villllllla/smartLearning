import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { Download, FileText, Plus, Search, Sparkles, Trash2 } from "lucide-react";

import { wikiApi } from "@/api/wiki";
import type { WikiSummary } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { BulkGenerateQuestionsDialog } from "./BulkGenerateQuestionsDialog";
import { Card, CardContent } from "@/components/ui/card";
import { Empty } from "@/components/Empty";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/layout/PageHeader";
import { toast } from "@/components/ui/toast";
import { cn, formatDateTime } from "@/lib/utils";
import { formatWikiPendingLabel, wikiHasPending } from "@/lib/wikiPending";

export function WikiListPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Set<number>>(() => new Set());
  const [bulkGenOpen, setBulkGenOpen] = useState(false);
  const selectAllRef = useRef<HTMLInputElement>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["wiki-list", q],
    queryFn: () => wikiApi.list({ q: q || undefined, limit: 50 }),
  });

  const items = data?.items ?? [];

  useEffect(() => {
    setSelected(new Set());
  }, [q]);

  useEffect(() => {
    const el = selectAllRef.current;
    if (!el) return;
    el.indeterminate =
      selected.size > 0 && selected.size < items.length && items.length > 0;
  }, [selected, items]);

  const allVisibleSelected = useMemo(
    () => items.length > 0 && items.every((w) => selected.has(w.id)),
    [items, selected],
  );

  const toggleOne = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAllVisible = () => {
    setSelected((prev) => {
      if (items.length === 0) return new Set();
      if (items.every((w) => prev.has(w.id))) {
        const next = new Set(prev);
        for (const w of items) next.delete(w.id);
        return next;
      }
      const next = new Set(prev);
      for (const w of items) next.add(w.id);
      return next;
    });
  };

  const clearSelection = () => setSelected(new Set());

  const remove = useMutation({
    mutationFn: (id: number) => wikiApi.remove(id),
    onSuccess: (_, id) => {
      toast.success("已删除");
      setSelected((prev) => {
        if (!prev.has(id)) return prev;
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
      qc.invalidateQueries({ queryKey: ["wiki-list"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const downloadOne = useMutation({
    mutationFn: (id: number) => wikiApi.download(id),
    onSuccess: () => toast.success("已开始下载"),
    onError: (e: Error) => toast.error(e.message),
  });

  const bulkRemove = useMutation({
    mutationFn: async (ids: number[]) => {
      const settled = await Promise.allSettled(ids.map((id) => wikiApi.remove(id)));
      const failed: { id: number; message: string }[] = [];
      settled.forEach((r, i) => {
        if (r.status === "rejected")
          failed.push({
            id: ids[i],
            message: r.reason instanceof Error ? r.reason.message : "删除失败",
          });
      });
      return { failed, ok: ids.length - failed.length };
    },
    onSuccess: (res) => {
      if (res.ok > 0) {
        toast.success(
          res.failed.length === 0
            ? `已删除 ${res.ok} 篇文档`
            : `已删除 ${res.ok} 篇,${res.failed.length} 篇失败`,
        );
      }
      if (res.failed.length > 0 && res.ok === 0) {
        toast.error(res.failed[0]?.message ?? "批量删除失败");
      }
      clearSelection();
      qc.invalidateQueries({ queryKey: ["wiki-list"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const selectedWikis: WikiSummary[] = useMemo(
    () => items.filter((w) => selected.has(w.id)),
    [items, selected],
  );

  const busy = remove.isPending || bulkRemove.isPending;

  return (
    <>
      <PageHeader
        title="知识库"
        description="上传 Markdown 笔记 → 浏览 / 检索 → 进入详情后可生成面试题"
        actions={
          <Button onClick={() => navigate("/wiki/upload")}>
            <Plus className="h-4 w-4" />
            上传 Markdown
          </Button>
        }
      />

      <div className="mx-auto max-w-5xl space-y-4 p-4 md:p-8">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="搜索标题或正文..."
              className="pl-9"
            />
          </div>
          {items.length > 0 && (
            <label className="flex shrink-0 cursor-pointer items-center gap-2 text-sm text-muted-foreground">
              <input
                ref={selectAllRef}
                type="checkbox"
                checked={allVisibleSelected}
                disabled={busy}
                onChange={toggleSelectAllVisible}
                className={cn(
                  "h-4 w-4 rounded border border-input bg-background",
                  "accent-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                )}
              />
              全选本页
            </label>
          )}
        </div>

        {selected.size > 0 && (
          <div
            className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-muted/40 px-3 py-2 text-sm"
            role="status"
          >
            <span className="text-foreground">已选 {selected.size} 篇</span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={clearSelection}
            >
              取消选择
            </Button>
            <Button
              type="button"
              variant="default"
              size="sm"
              disabled={busy}
              onClick={() => setBulkGenOpen(true)}
            >
              <Sparkles className="mr-1 h-3.5 w-3.5" />
              批量生成面试题
            </Button>
            <Button
              type="button"
              variant="destructive"
              size="sm"
              disabled={busy}
              onClick={() => {
                const ids = [...selected];
                const titles = items
                  .filter((w) => ids.includes(w.id))
                  .map((w) => w.title);
                const preview =
                  titles.length <= 3
                    ? titles.map((t) => `「${t}」`).join("、")
                    : `${ids.length} 篇(例如 ${titles
                        .slice(0, 2)
                        .map((t) => `「${t}」`)
                        .join("、")} 等)`;
                if (
                  confirm(`确认删除 ${preview}?(软删除,与单篇删除规则相同)`)
                ) {
                  bulkRemove.mutate(ids);
                }
              }}
            >
              <Trash2 className="mr-1 h-3.5 w-3.5" />
              删除所选
            </Button>
          </div>
        )}

        {isLoading ? (
          <div className="text-sm text-muted-foreground">加载中...</div>
        ) : items.length === 0 ? (
          <Empty
            title={q ? "没有匹配的 wiki" : "知识库还是空的"}
            description={
              q
                ? "尝试换一个关键词,或清空搜索框查看全部。"
                : "把你的 Markdown 笔记拖进来,系统会解析标题与目录,后续可一键生成面试题。"
            }
            action={
              <Button onClick={() => navigate("/wiki/upload")}>
                <Plus className="h-4 w-4" />
                立即上传
              </Button>
            }
          />
        ) : (
          <div className="grid gap-3">
            {items.map((w) => (
              <Card
                key={w.id}
                className={cn(
                  "transition-shadow hover:shadow-md",
                  selected.has(w.id) && "ring-2 ring-primary/30",
                )}
              >
                <CardContent className="flex items-start gap-3 p-5">
                  <input
                    type="checkbox"
                    checked={selected.has(w.id)}
                    disabled={busy}
                    onChange={() => toggleOne(w.id)}
                    aria-label={`选择 ${w.title}`}
                    className={cn(
                      "mt-1 h-4 w-4 shrink-0 rounded border border-input bg-background",
                      "accent-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    )}
                  />
                  <Link to={`/wiki/${w.id}`} className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <FileText className="h-4 w-4 shrink-0 text-primary" />
                      <span className="truncate text-base font-medium">
                        {w.title}
                      </span>
                      {(w.bank_question_count ?? 0) > 0 && (
                        <Badge variant="secondary" className="shrink-0 text-[10px]">
                          已出题 {w.bank_question_count}
                        </Badge>
                      )}
                      {wikiHasPending(w) && w.pending_batch_id ? (
                        <Link
                          to={`/bank/candidates/${w.pending_batch_id}`}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <Badge
                            variant="outline"
                            className="shrink-0 cursor-pointer text-[10px] hover:bg-accent"
                          >
                            {formatWikiPendingLabel(w)} · 查看
                          </Badge>
                        </Link>
                      ) : wikiHasPending(w) ? (
                        <Badge variant="outline" className="shrink-0 text-[10px]">
                          {formatWikiPendingLabel(w)}
                        </Badge>
                      ) : null}
                    </div>
                    {w.excerpt && (
                      <p className="mt-2 line-clamp-2 text-sm text-muted-foreground">
                        {w.excerpt}
                      </p>
                    )}
                    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                      <span>{w.word_count} 字</span>
                      <span>更新于 {formatDateTime(w.updated_at)}</span>
                    </div>
                  </Link>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="下载"
                    disabled={busy || downloadOne.isPending}
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      downloadOne.mutate(w.id);
                    }}
                  >
                    <Download className="h-4 w-4 text-muted-foreground" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="删除"
                    disabled={busy}
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      if (confirm(`确认删除「${w.title}」?(软删除,可恢复)`)) {
                        remove.mutate(w.id);
                      }
                    }}
                  >
                    <Trash2 className="h-4 w-4 text-muted-foreground hover:text-destructive" />
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      <BulkGenerateQuestionsDialog
        open={bulkGenOpen}
        wikis={selectedWikis}
        onOpenChange={setBulkGenOpen}
        onDone={() => {
          qc.invalidateQueries({ queryKey: ["wiki-list"] });
          qc.invalidateQueries({ queryKey: ["bank-questions"] });
        }}
      />
    </>
  );
}
