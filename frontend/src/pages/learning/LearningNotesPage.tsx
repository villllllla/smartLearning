import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BrainCircuit,
  CheckCircle2,
  Loader2,
  RotateCcw,
  Send,
  Trash2,
} from "lucide-react";

import {
  learningNotesApi,
  type LearningNoteSummary,
} from "@/api/learningNotes";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

type Filter = "all" | "due" | "active";

const LEARNING_KEY = ["learning-notes"];

export function LearningNotesPage() {
  const qc = useQueryClient();
  const [draft, setDraft] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

  const listQ = useQuery({
    queryKey: [...LEARNING_KEY, filter],
    queryFn: () =>
      learningNotesApi.list({
        only_due: filter === "due",
        // 已掌握不再被排除出待复习队列，只是降权排后。
        include_mastered: filter !== "active",
        limit: 100,
      }),
  });

  function invalidate() {
    qc.invalidateQueries({ queryKey: LEARNING_KEY });
  }

  const create = useMutation({
    mutationFn: (raw: string) => learningNotesApi.create({ raw_input: raw }),
    onSuccess: (note) => {
      setDraft("");
      invalidate();
      const issues = note.review?.issues?.length ?? 0;
      toast.success(
        issues > 0
          ? `已保存并发现 ${issues} 处需注意，已加入复习计划`
          : "已检验、结构化并加入复习计划",
      );
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const reviewed = useMutation({
    mutationFn: (id: number) => learningNotesApi.markReviewed(id),
    onSuccess: () => {
      invalidate();
      toast.success("已记一次复习，下次推送时间已顺延");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const master = useMutation({
    mutationFn: (v: { id: number; mastered: boolean }) =>
      learningNotesApi.setMastered(v.id, v.mastered),
    onSuccess: () => invalidate(),
    onError: (e: Error) => toast.error(e.message),
  });

  const remove = useMutation({
    mutationFn: (id: number) => learningNotesApi.remove(id),
    onSuccess: () => {
      invalidate();
      toast.success("已删除");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const items = listQ.data?.items ?? [];
  const dueToday = listQ.data?.due_today ?? 0;

  const filtered = useMemo(() => {
    if (filter === "active") return items.filter((n) => !n.mastered);
    return items;
  }, [items, filter]);

  function submit() {
    const text = draft.trim();
    if (text.length < 8) {
      toast.error("请输入更完整的学习总结（至少 8 个字）");
      return;
    }
    create.mutate(text);
  }

  return (
    <>
      <PageHeader
        title="学习日志"
        description="记录每日学习总结 → 大模型检验+结构化+打标签 → 次日起按 1/3/7/15/30 天间隔复习推送"
      />

      <div className="mx-auto max-w-5xl space-y-6 p-4 md:p-8">
        <Card>
          <CardContent className="space-y-3 p-5">
            <div className="flex items-center gap-2 text-sm font-medium">
              <BrainCircuit className="h-4 w-4" />
              今天学到了什么？
            </div>
            <Textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={5}
              placeholder="例如：今天学习了 Redis 的持久化机制，RDB 是快照、AOF 是追加日志，二者可以混合使用……"
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === "Enter") submit();
              }}
            />
            <div className="flex items-center justify-between">
              <p className="text-xs text-muted-foreground">
                提交后由模型检验事实、提炼要点并打标签。⌘/Ctrl + Enter 快速提交。
                也可在飞书发「总结 …」。
              </p>
              <Button onClick={submit} disabled={create.isPending}>
                {create.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Send className="mr-2 h-4 w-4" />
                )}
                检验并保存
              </Button>
            </div>
          </CardContent>
        </Card>

        <div className="flex flex-wrap items-center gap-2">
          {(
            [
              { id: "all", label: "全部" },
              { id: "active", label: "未掌握" },
              { id: "due", label: `今日待复习${dueToday ? ` (${dueToday})` : ""}` },
            ] as { id: Filter; label: string }[]
          ).map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setFilter(t.id)}
              className={cn(
                "rounded-full border px-3 py-1 text-sm",
                filter === t.id
                  ? "border-primary bg-primary/10 text-foreground"
                  : "text-muted-foreground hover:bg-accent",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>

        {listQ.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            加载中…
          </div>
        ) : filtered.length === 0 ? (
          <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
            还没有学习总结。在上方写下今天学到的内容试试。
          </div>
        ) : (
          <div className="space-y-3">
            {filtered.map((note) => (
              <NoteCard
                key={note.id}
                note={note}
                onReviewed={() => reviewed.mutate(note.id)}
                onMaster={() =>
                  master.mutate({ id: note.id, mastered: !note.mastered })
                }
                onDelete={() => {
                  if (window.confirm("确定删除这条学习总结？")) remove.mutate(note.id);
                }}
                busy={reviewed.isPending || master.isPending || remove.isPending}
              />
            ))}
          </div>
        )}
      </div>
    </>
  );
}

function NoteCard({
  note,
  onReviewed,
  onMaster,
  onDelete,
  busy,
}: {
  note: LearningNoteSummary;
  onReviewed: () => void;
  onMaster: () => void;
  onDelete: () => void;
  busy: boolean;
}) {
  const [open, setOpen] = useState(false);
  const detailQ = useQuery({
    queryKey: ["learning-note", note.id],
    queryFn: () => learningNotesApi.get(note.id),
    enabled: open,
  });
  const next = note.next_review_at
    ? new Date(note.next_review_at).toLocaleDateString()
    : null;
  const created = note.created_at
    ? new Date(note.created_at).toLocaleString(undefined, {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    : null;
  const issues = detailQ.data?.review?.issues ?? [];
  const corrections = detailQ.data?.review?.corrections ?? [];
  const suggestions = detailQ.data?.review?.suggestions ?? [];

  return (
    <Card>
      <CardContent className="space-y-3 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 space-y-1">
            <div className="flex items-center gap-2">
              <span className="font-semibold">{note.title}</span>
              {note.mastered ? (
                <Badge variant="outline" className="text-emerald-600">
                  已掌握
                </Badge>
              ) : null}
              {note.category ? (
                <Badge variant="outline">{note.category}</Badge>
              ) : null}
            </div>
            {note.summary ? (
              <p className="text-sm text-muted-foreground">{note.summary}</p>
            ) : null}
          </div>
          <div className="shrink-0 text-right text-xs text-muted-foreground">
            {created ? <div>记录于 {created}</div> : null}
            {note.quality_score != null ? <div>评分 {note.quality_score}</div> : null}
            <div>复习 {note.review_count} 次</div>
            {next ? (
              <div>
                下次 {next}
                {note.mastered ? "（低频抽查）" : ""}
              </div>
            ) : null}
          </div>
        </div>

        {note.key_points?.length ? (
          <ul className="ml-4 list-disc space-y-1 text-sm">
            {note.key_points.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        ) : null}

        {note.tags?.length ? (
          <div className="flex flex-wrap gap-1.5">
            {note.tags.map((t) => (
              <Badge key={t.id} variant="secondary" className="text-xs">
                {t.name}
              </Badge>
            ))}
          </div>
        ) : null}

        {open ? (
          <div className="space-y-2 rounded-md border bg-muted/30 p-3 text-sm">
            {detailQ.isLoading ? (
              <div className="flex items-center gap-2 text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> 加载详情…
              </div>
            ) : (
              <>
                {issues.length > 0 ? (
                  <div>
                    <div className="font-medium text-amber-600">检验发现</div>
                    <ul className="ml-4 list-disc">
                      {issues.map((x, i) => (
                        <li key={i}>{x}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {corrections.length > 0 ? (
                  <div>
                    <div className="font-medium">纠正</div>
                    <ul className="ml-4 list-disc">
                      {corrections.map((x, i) => (
                        <li key={i}>{x}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {suggestions.length > 0 ? (
                  <div>
                    <div className="font-medium">建议</div>
                    <ul className="ml-4 list-disc">
                      {suggestions.map((x, i) => (
                        <li key={i}>{x}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {issues.length === 0 &&
                corrections.length === 0 &&
                suggestions.length === 0 ? (
                  <div className="text-muted-foreground">模型未提出额外检验意见。</div>
                ) : null}
                {detailQ.data?.raw_input ? (
                  <div>
                    <div className="font-medium">原始输入</div>
                    <p className="whitespace-pre-wrap text-muted-foreground">
                      {detailQ.data.raw_input}
                    </p>
                  </div>
                ) : null}
              </>
            )}
          </div>
        ) : null}

        <div className="flex flex-wrap gap-2 pt-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setOpen((v) => !v)}
          >
            {open ? "收起" : "检验详情 / 原文"}
          </Button>
          {!note.mastered ? (
            <Button
              variant="outline"
              size="sm"
              onClick={onReviewed}
              disabled={busy}
            >
              <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
              记一次复习
            </Button>
          ) : null}
          <Button variant="outline" size="sm" onClick={onMaster} disabled={busy}>
            <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
            {note.mastered ? "重新复习" : "已掌握"}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="text-destructive"
            onClick={onDelete}
            disabled={busy}
          >
            <Trash2 className="mr-1.5 h-3.5 w-3.5" />
            删除
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
