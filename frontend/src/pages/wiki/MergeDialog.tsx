/**
 * MergeDialog — 3-pane conflict resolver (PRD §6.1.2).
 *
 * Layout principles:
 * - Top: header + summary (clean count / conflict count / fast-forward badge)
 * - Body: scrollable list of hunks. For each *conflict* hunk we show three
 *   columns side-by-side (base / ours=main / theirs=branch); user clicks
 *   one to lock that side OR types into a custom textarea. Clean hunks
 *   render as a green collapsed row.
 * - Footer: commit message + 「合并到 main」 button.
 *
 * The dialog content is wide; on small screens columns stack vertically.
 */
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  GitMerge,
  Loader2,
  Wand2,
} from "lucide-react";

import {
  branchApi,
  type BranchSummary,
  type MergeHunk,
  type MergePreview,
} from "@/api/wiki";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  branch: BranchSummary | null;
  wikiId: number;
  onOpenChange: (v: boolean) => void;
  onMerged: () => void;
}

type Choice =
  | { kind: "ours" }
  | { kind: "theirs" }
  | { kind: "base" }
  | { kind: "custom"; text: string };

function resolutionText(h: MergeHunk, c: Choice | undefined): string | null {
  if (!c) return null;
  if (c.kind === "ours") return h.ours_text;
  if (c.kind === "theirs") return h.theirs_text;
  if (c.kind === "base") return h.base_text;
  return c.text;
}

export function MergeDialog({ open, branch, wikiId, onOpenChange, onMerged }: Props) {
  const qc = useQueryClient();
  const [choices, setChoices] = useState<Record<number, Choice>>({});
  const [message, setMessage] = useState("");

  const previewQ = useQuery({
    queryKey: ["merge-preview", branch?.id ?? null],
    queryFn: () => branchApi.mergePreview(branch!.id),
    enabled: open && branch !== null && branch.name !== "main",
  });

  // Reset state when dialog opens for a different branch
  useEffect(() => {
    if (open && branch) {
      setChoices({});
      setMessage(`merge branch '${branch.name}' into main`);
    }
  }, [open, branch?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const merge = useMutation({
    mutationFn: () => {
      if (!branch || !previewQ.data) throw new Error("no preview");
      const resolutions: Record<number, string> = {};
      if (previewQ.data.has_conflict) {
        for (const h of previewQ.data.hunks) {
          if (h.kind !== "conflict") continue;
          const text = resolutionText(h, choices[h.id]);
          if (text === null) throw new Error(`hunk #${h.id} 未选择解决方式`);
          resolutions[h.id] = text;
        }
      }
      return branchApi.merge(branch.id, {
        expected_main_head_id: previewQ.data.main_head_commit_id,
        message: message.trim() || `merge branch '${branch.name}' into main`,
        resolutions: previewQ.data.has_conflict ? resolutions : null,
      });
    },
    onSuccess: () => {
      toast.success("已合并到 main");
      qc.invalidateQueries({ queryKey: ["wiki", wikiId] });
      qc.invalidateQueries({ queryKey: ["branch-list", wikiId] });
      qc.invalidateQueries({ queryKey: ["branch-content"] });
      onMerged();
      onOpenChange(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (!open || !branch) return null;

  const data = previewQ.data;
  const conflictHunks = data?.hunks.filter((h) => h.kind === "conflict") ?? [];
  const allConflictsResolved = conflictHunks.every((h) => choices[h.id] !== undefined);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-3 md:p-6"
      onClick={() => !merge.isPending && onOpenChange(false)}
    >
      <div
        className="flex h-full max-h-[92vh] w-full max-w-6xl flex-col rounded-xl border border-border bg-background shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <header className="flex flex-wrap items-center gap-3 border-b border-border p-4 md:p-6">
          <GitMerge className="h-5 w-5 text-primary" />
          <div className="min-w-0">
            <div className="text-base font-semibold">
              合并 <code className="mx-1 rounded bg-muted px-1.5 py-0.5">{branch.name}</code> →{" "}
              <code className="mx-1 rounded bg-muted px-1.5 py-0.5">main</code>
            </div>
            <Summary preview={data} loading={previewQ.isLoading} />
          </div>
          <div className="ml-auto flex gap-2">
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={merge.isPending}
            >
              取消
            </Button>
            <Button
              disabled={
                merge.isPending ||
                !data ||
                (data.has_conflict && !allConflictsResolved)
              }
              onClick={() => merge.mutate()}
              className="gap-2"
            >
              {merge.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <GitMerge className="h-4 w-4" />
              )}
              {data?.has_conflict ? "解决并合并" : "合并到 main"}
            </Button>
          </div>
        </header>

        {/* Body */}
        <div className="flex-1 overflow-y-auto bg-muted/30 p-3 md:p-6">
          {previewQ.isLoading && (
            <div className="flex items-center justify-center py-16 text-sm text-muted-foreground">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 加载预览…
            </div>
          )}
          {previewQ.isError && (
            <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
              {(previewQ.error as Error).message}
            </div>
          )}

          {data && data.hunks.length === 0 && !data.has_conflict && (
            <div className="rounded-md border border-emerald-500/40 bg-emerald-500/5 p-6 text-center text-sm text-emerald-700 dark:text-emerald-300">
              <CheckCircle2 className="mx-auto mb-2 h-6 w-6" />
              <div className="font-medium">无差异 / 快进合并</div>
              <p className="mt-1 text-xs">
                main 尚未变化（或本分支与 main 完全一致），合并将直接把 main 指针指向本分支 HEAD。
              </p>
            </div>
          )}

          {data?.hunks.map((h, idx) => (
            <HunkCard
              key={h.id}
              index={idx + 1}
              total={data.hunks.length}
              hunk={h}
              choice={choices[h.id]}
              onChoose={(c) => setChoices((s) => ({ ...s, [h.id]: c }))}
            />
          ))}
        </div>

        {/* Footer */}
        <footer className="flex flex-col gap-3 border-t border-border p-4 md:flex-row md:items-end md:p-6">
          <div className="flex-1">
            <Label htmlFor="merge-msg">合并提交说明</Label>
            <Input
              id="merge-msg"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder={`merge branch '${branch.name}' into main`}
            />
          </div>
          {data?.has_conflict && (
            <div className="text-xs text-muted-foreground">
              {Object.keys(choices).length}/{conflictHunks.length} 个冲突已选择
              {allConflictsResolved && (
                <Badge variant="secondary" className="ml-2 gap-1">
                  <CheckCircle2 className="h-3 w-3" /> 全部解决
                </Badge>
              )}
            </div>
          )}
        </footer>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------

function Summary({
  preview,
  loading,
}: {
  preview: MergePreview | undefined;
  loading: boolean;
}) {
  if (loading || !preview)
    return (
      <div className="text-xs text-muted-foreground">加载中…</div>
    );
  const clean = preview.hunks.length - preview.conflict_count;
  return (
    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      <span>
        共 <strong className="text-foreground">{preview.hunks.length}</strong> 处差异
      </span>
      <Badge variant={clean > 0 ? "secondary" : "outline"} className="gap-1">
        <CheckCircle2 className="h-3 w-3" /> 干净 {clean}
      </Badge>
      {preview.conflict_count > 0 ? (
        <Badge variant="destructive" className="gap-1">
          <AlertTriangle className="h-3 w-3" /> 冲突 {preview.conflict_count}
        </Badge>
      ) : (
        <Badge variant="secondary" className="gap-1 text-emerald-700 dark:text-emerald-300">
          <Wand2 className="h-3 w-3" /> 可自动合并
        </Badge>
      )}
      {preview.base_commit_id !== null && (
        <span>· 共同祖先 commit#{preview.base_commit_id}</span>
      )}
    </div>
  );
}

function HunkCard({
  index,
  total,
  hunk,
  choice,
  onChoose,
}: {
  index: number;
  total: number;
  hunk: MergeHunk;
  choice: Choice | undefined;
  onChoose: (c: Choice) => void;
}) {
  if (hunk.kind === "clean") {
    return (
      <details className="mb-3 rounded-md border border-border bg-background">
        <summary className="flex cursor-pointer items-center gap-2 px-4 py-2 text-sm">
          <CheckCircle2 className="h-4 w-4 text-emerald-500" />
          <span className="font-medium">
            #{index}/{total} 干净修改（已自动采用）
          </span>
          <span className="ml-auto text-xs text-muted-foreground">
            base 行 {hunk.base_start}–{hunk.base_end}
          </span>
        </summary>
        <pre className="overflow-x-auto whitespace-pre-wrap break-words border-t border-border bg-muted/40 p-3 text-xs">
          {hunk.resolved ?? ""}
        </pre>
      </details>
    );
  }

  return (
    <div className="mb-3 overflow-hidden rounded-md border border-destructive/50 bg-background">
      <div className="flex items-center gap-2 border-b border-border bg-destructive/10 px-4 py-2 text-sm">
        <AlertTriangle className="h-4 w-4 text-destructive" />
        <span className="font-medium text-destructive">
          #{index}/{total} 冲突
        </span>
        <span className="ml-auto text-xs text-muted-foreground">
          base 行 {hunk.base_start}–{hunk.base_end}
        </span>
      </div>

      <div className="grid grid-cols-1 gap-3 p-3 md:grid-cols-3">
        <ChoiceColumn
          title="Base（共同祖先）"
          tone="neutral"
          text={hunk.base_text}
          active={choice?.kind === "base"}
          onSelect={() => onChoose({ kind: "base" })}
          actionLabel="保留 base"
        />
        <ChoiceColumn
          title="Ours · main 当前"
          tone="ours"
          text={hunk.ours_text}
          active={choice?.kind === "ours"}
          onSelect={() => onChoose({ kind: "ours" })}
          actionLabel="选 main"
        />
        <ChoiceColumn
          title="Theirs · 本分支"
          tone="theirs"
          text={hunk.theirs_text}
          active={choice?.kind === "theirs"}
          onSelect={() => onChoose({ kind: "theirs" })}
          actionLabel="选本分支"
        />
      </div>

      <div className="border-t border-border bg-muted/30 px-3 py-2">
        <details>
          <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
            或自定义解决文本（直接编辑覆盖三栏）
          </summary>
          <Textarea
            className="mt-2 font-mono text-xs"
            rows={4}
            value={choice?.kind === "custom" ? choice.text : ""}
            onChange={(e) => onChoose({ kind: "custom", text: e.target.value })}
            placeholder="自定义合并后的此片段内容…"
          />
        </details>
      </div>
    </div>
  );
}

function ChoiceColumn({
  title,
  tone,
  text,
  active,
  onSelect,
  actionLabel,
}: {
  title: string;
  tone: "neutral" | "ours" | "theirs";
  text: string;
  active: boolean;
  onSelect: () => void;
  actionLabel: string;
}) {
  const headerColor = useMemo(
    () =>
      tone === "ours"
        ? "text-blue-600 dark:text-blue-400"
        : tone === "theirs"
          ? "text-violet-600 dark:text-violet-400"
          : "text-muted-foreground",
    [tone],
  );
  return (
    <div
      className={cn(
        "flex flex-col rounded-md border bg-background",
        active ? "border-primary ring-2 ring-primary/30" : "border-border",
      )}
    >
      <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-1.5">
        <span className={cn("text-xs font-semibold uppercase tracking-wider", headerColor)}>
          {title}
        </span>
        <Button
          size="sm"
          variant={active ? "default" : "outline"}
          className="h-6 px-2 text-[11px]"
          onClick={onSelect}
        >
          {active ? "已选" : actionLabel}
        </Button>
      </div>
      <pre className="max-h-48 min-h-[3rem] overflow-auto whitespace-pre-wrap break-words p-3 text-xs">
        {text === "" ? <span className="italic text-muted-foreground">（空）</span> : text}
      </pre>
    </div>
  );
}
