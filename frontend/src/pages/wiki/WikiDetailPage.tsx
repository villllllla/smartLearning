/**
 * Wiki detail with branching (PRD §6.1.2).
 *
 * UX:
 *  - Header carries: branch dropdown, [新建分支], (when editing) [取消]/[提交],
 *    (on non-main branches) [合并到 main], [生成面试题].
 *  - View mode = rendered Markdown for the *currently selected branch's* HEAD.
 *  - Edit mode = textarea preloaded with HEAD content; commit creates a new
 *    commit (CAS-guarded by `expected_parent_commit_id` from when we loaded).
 *  - Right-side drawer keeps TOC + branch list with HEAD + delete actions.
 */
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Download,
  GitBranch,
  GitMerge,
  ListTree,
  Pencil,
  Plus,
  Save,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";

import {
  branchApi,
  type BranchSummary,
  wikiApi,
} from "@/api/wiki";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { MarkdownView } from "@/components/MarkdownView";
import { PageHeader } from "@/components/layout/PageHeader";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/components/ui/toast";
import { cn, formatDateTime } from "@/lib/utils";
import { formatWikiPendingLabel, wikiHasPending } from "@/lib/wikiPending";
import { GenerateQuestionsDialog } from "./GenerateQuestionsDialog";
import { MergeDialog } from "./MergeDialog";
import { NewBranchDialog } from "./NewBranchDialog";

type DrawerPanel = null | "toc" | "branches";

export function WikiDetailPage() {
  const { id } = useParams<{ id: string }>();
  const wikiId = Number(id);
  const qc = useQueryClient();

  const [panel, setPanel] = useState<DrawerPanel>(null);
  const [generating, setGenerating] = useState(false);
  const [creatingBranch, setCreatingBranch] = useState(false);
  const [merging, setMerging] = useState(false);
  const [activeBranchId, setActiveBranchId] = useState<number | null>(null);

  // Edit state
  const [editing, setEditing] = useState(false);
  const [draftContent, setDraftContent] = useState("");
  const [commitMessage, setCommitMessage] = useState("");

  const wikiQ = useQuery({
    queryKey: ["wiki", wikiId],
    queryFn: () => wikiApi.get(wikiId),
    enabled: !Number.isNaN(wikiId),
  });

  const branchListQ = useQuery({
    queryKey: ["branch-list", wikiId],
    queryFn: () => branchApi.list(wikiId),
    enabled: !Number.isNaN(wikiId),
  });

  // Default-select main once branches load
  useEffect(() => {
    if (activeBranchId !== null) return;
    const list = branchListQ.data ?? [];
    const main = list.find((b) => b.name === "main") ?? list[0];
    if (main) setActiveBranchId(main.id);
  }, [branchListQ.data, activeBranchId]);

  const branchContentQ = useQuery({
    queryKey: ["branch-content", activeBranchId],
    queryFn: () => branchApi.get(activeBranchId!),
    enabled: activeBranchId !== null,
  });

  const branches = branchListQ.data ?? [];
  const activeBranch: BranchSummary | null = useMemo(
    () => branches.find((b) => b.id === activeBranchId) ?? null,
    [branches, activeBranchId],
  );

  const isMain = activeBranch?.name === "main";

  // When entering edit mode, snapshot the loaded HEAD content
  const enterEdit = () => {
    if (!branchContentQ.data) return;
    setDraftContent(branchContentQ.data.content_md);
    setCommitMessage("");
    setEditing(true);
  };
  const cancelEdit = () => {
    setEditing(false);
    setDraftContent("");
    setCommitMessage("");
  };

  const commit = useMutation({
    mutationFn: () => {
      if (!activeBranchId || !branchContentQ.data) {
        throw new Error("分支未加载");
      }
      return branchApi.commit(activeBranchId, {
        content_md: draftContent,
        message: commitMessage.trim() || "edit",
        expected_parent_commit_id: branchContentQ.data.head_commit_id,
      });
    },
    onSuccess: () => {
      toast.success("已提交");
      setEditing(false);
      qc.invalidateQueries({ queryKey: ["branch-content", activeBranchId] });
      qc.invalidateQueries({ queryKey: ["branch-list", wikiId] });
      // If main got committed, the wiki summary changed too
      if (isMain) qc.invalidateQueries({ queryKey: ["wiki", wikiId] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const deleteBranch = useMutation({
    mutationFn: (branchId: number) => branchApi.remove(branchId),
    onSuccess: (_d, branchId) => {
      toast.success("已删除分支");
      if (activeBranchId === branchId) {
        const main = branches.find((b) => b.name === "main");
        setActiveBranchId(main?.id ?? null);
      }
      qc.invalidateQueries({ queryKey: ["branch-list", wikiId] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const wiki = wikiQ.data;

  const downloadWiki = useMutation({
    mutationFn: () => wikiApi.download(wikiId, activeBranchId),
    onSuccess: () => toast.success("已开始下载"),
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <>
      <PageHeader
        title={wiki?.title ?? (wikiQ.isLoading ? "加载中..." : "未找到")}
        description={
          wiki ? (
            <span className="flex flex-wrap items-center gap-2">
              <span>
                {wiki.word_count} 字 · 更新于 {formatDateTime(wiki.updated_at)}
              </span>
              {(wiki.bank_question_count ?? 0) > 0 && (
                <Badge variant="secondary">已出题 {wiki.bank_question_count}</Badge>
              )}
              {wikiHasPending(wiki) && (
                <Badge variant="outline" title="最新一批候选数，与「查看候选」页一致">
                  {formatWikiPendingLabel(wiki)}
                </Badge>
              )}
              {activeBranch && (
                <Badge variant={isMain ? "default" : "secondary"} className="gap-1">
                  <GitBranch className="h-3 w-3" />
                  {activeBranch.name}
                  {branchContentQ.data?.head_commit_id != null && (
                    <span className="ml-1 opacity-70">
                      @{branchContentQ.data.head_commit_id}
                    </span>
                  )}
                </Badge>
              )}
            </span>
          ) : undefined
        }
        actions={
          <>
            <Button variant="outline" asChild>
              <Link to="/wiki">
                <ArrowLeft className="h-4 w-4" />
                返回
              </Link>
            </Button>

            <Select
              value={activeBranchId ? String(activeBranchId) : ""}
              onChange={(e) => {
                if (editing) return; // guard against losing draft
                setActiveBranchId(Number(e.target.value));
              }}
              disabled={editing || branches.length === 0}
              title={editing ? "编辑中无法切换分支" : undefined}
              className="h-10 w-auto min-w-[10rem]"
            >
              {branches.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </Select>

            <Button
              variant="ghost"
              size="icon"
              title="新建分支"
              onClick={() => setCreatingBranch(true)}
              disabled={!wiki || editing}
            >
              <Plus className="h-4 w-4" />
            </Button>

            <Button
              variant="outline"
              onClick={() => downloadWiki.mutate()}
              disabled={!wiki || downloadWiki.isPending}
              title="下载当前分支 Markdown（含图片时打包为 zip）"
            >
              <Download className="h-4 w-4" />
              下载
            </Button>

            {!editing && activeBranch && (
              <Button
                variant="outline"
                onClick={enterEdit}
                disabled={!branchContentQ.data}
                title={
                  isMain
                    ? "在 main 上直接编辑会立即影响题库的 source_commit_id 引用"
                    : undefined
                }
              >
                <Pencil className="h-4 w-4" />
                编辑
              </Button>
            )}
            {editing && (
              <Button variant="ghost" onClick={cancelEdit} disabled={commit.isPending}>
                <X className="h-4 w-4" />
                取消
              </Button>
            )}
            {editing && (
              <Button onClick={() => commit.mutate()} disabled={commit.isPending}>
                <Save className="h-4 w-4" />
                提交
              </Button>
            )}

            {!editing && activeBranch && !isMain && (
              <Button
                variant="secondary"
                onClick={() => setMerging(true)}
                title="合并到 main，必要时三栏解决冲突"
              >
                <GitMerge className="h-4 w-4" />
                合并到 main
              </Button>
            )}

            <Button
              variant={panel === "toc" ? "secondary" : "ghost"}
              size="icon"
              aria-label="目录"
              title="目录"
              onClick={() => setPanel(panel === "toc" ? null : "toc")}
            >
              <ListTree className="h-4 w-4" />
            </Button>
            <Button
              variant={panel === "branches" ? "secondary" : "ghost"}
              size="icon"
              aria-label="分支与版本"
              title="分支与版本"
              onClick={() =>
                setPanel(panel === "branches" ? null : "branches")
              }
            >
              <GitBranch className="h-4 w-4" />
            </Button>
            {wiki && wikiHasPending(wiki) && wiki.pending_batch_id ? (
              <Button variant="outline" asChild>
                <Link to={`/bank/candidates/${wiki.pending_batch_id}`}>
                  查看候选 ({wiki.pending_candidate_count})
                </Link>
              </Button>
            ) : null}
            <Button
              onClick={() => setGenerating(true)}
              disabled={!wiki || editing}
              title="基于本 wiki 当前内容生成候选面试题"
            >
              <Sparkles className="h-4 w-4" />
              生成面试题
            </Button>
          </>
        }
      />

      <div className="mx-auto flex w-full max-w-7xl gap-6 p-4 md:p-8">
        <div className="min-w-0 flex-1">
          {wikiQ.isLoading && (
            <div className="text-sm text-muted-foreground">加载中...</div>
          )}
          {wikiQ.isError && (
            <Card>
              <CardContent className="p-6 text-sm text-destructive">
                {(wikiQ.error as Error)?.message ?? "加载失败"}
              </CardContent>
            </Card>
          )}

          {wiki && !editing && (
            <Card>
              <CardContent className="p-5 md:p-8">
                {branchContentQ.isLoading ? (
                  <div className="text-sm text-muted-foreground">分支内容加载中…</div>
                ) : (
                  <MarkdownView
                    source={branchContentQ.data?.content_md ?? ""}
                    wikiAssetBase={`/api/wiki/${wikiId}/assets`}
                  />
                )}
              </CardContent>
            </Card>
          )}

          {wiki && editing && (
            <Card>
              <CardContent className="space-y-3 p-5 md:p-6">
                <div className="grid gap-2 sm:grid-cols-[1fr_auto] sm:items-end">
                  <div className="space-y-1.5">
                    <Label htmlFor="commit-msg">提交说明</Label>
                    <Input
                      id="commit-msg"
                      placeholder="edit · fix typo · refine §3 ..."
                      value={commitMessage}
                      onChange={(e) => setCommitMessage(e.target.value)}
                    />
                  </div>
                  <div className="text-xs text-muted-foreground sm:pb-2">
                    parent commit#{branchContentQ.data?.head_commit_id ?? "-"} · 提交时若 HEAD 已变会拒绝并提示刷新
                  </div>
                </div>
                <Textarea
                  className="min-h-[60vh] font-mono text-sm leading-6"
                  value={draftContent}
                  onChange={(e) => setDraftContent(e.target.value)}
                  spellCheck={false}
                />
                <p className="text-[11px] text-muted-foreground">
                  Markdown · 提交后会创建新的 commit;在 main 上提交会更新 wiki 元数据(标题、字数、摘要)。
                </p>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Drawer */}
        <aside
          className={cn(
            "hidden w-72 shrink-0 lg:block",
            panel === null && "lg:hidden",
          )}
        >
          {panel === "toc" && wiki && (
            <Card>
              <CardContent className="p-4">
                <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  目录
                </div>
                {wiki.toc.length === 0 && (
                  <div className="text-sm text-muted-foreground">无标题</div>
                )}
                <ul className="space-y-1 text-sm">
                  {wiki.toc.map((t, i) => (
                    <li
                      key={`${t.anchor}-${i}`}
                      style={{ paddingLeft: `${(t.level - 1) * 12}px` }}
                    >
                      <a
                        href={`#${t.anchor}`}
                        className="block truncate text-muted-foreground hover:text-foreground"
                      >
                        {t.text}
                      </a>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}

          {panel === "branches" && wiki && (
            <Card>
              <CardContent className="p-4">
                <div className="mb-2 flex items-center justify-between">
                  <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    分支
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 px-2"
                    onClick={() => setCreatingBranch(true)}
                    disabled={editing}
                  >
                    <Plus className="h-3.5 w-3.5" />
                    新建
                  </Button>
                </div>
                <ul className="space-y-1.5 text-sm">
                  {branches.map((b) => {
                    const active = b.id === activeBranchId;
                    return (
                      <li
                        key={b.id}
                        className={cn(
                          "flex items-center justify-between rounded border p-2 transition-colors",
                          active
                            ? "border-primary bg-primary/10"
                            : "border-border hover:bg-muted",
                        )}
                      >
                        <button
                          type="button"
                          className="flex min-w-0 items-center gap-2 text-left"
                          onClick={() => !editing && setActiveBranchId(b.id)}
                          disabled={editing}
                        >
                          <GitBranch className="h-3.5 w-3.5 text-muted-foreground" />
                          <span className="truncate font-medium">{b.name}</span>
                        </button>
                        <div className="flex items-center gap-1.5">
                          <span className="text-[11px] text-muted-foreground">
                            #{b.head_commit_id ?? "-"}
                          </span>
                          {b.name !== "main" && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-6 w-6"
                              title={`删除分支 ${b.name}`}
                              onClick={() => {
                                if (
                                  confirm(`确定删除分支 ${b.name}？历史 commit 会一并清理。`)
                                ) {
                                  deleteBranch.mutate(b.id);
                                }
                              }}
                              disabled={editing}
                            >
                              <Trash2 className="h-3.5 w-3.5 text-destructive" />
                            </Button>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ul>
                <p className="mt-3 text-[11px] text-muted-foreground">
                  在分支上编辑 → 点「合并到 main」走三栏冲突解决；main 上直接提交会立即更新 wiki 元数据并影响后续生成的题目 source_commit_id。
                </p>
              </CardContent>
            </Card>
          )}
        </aside>
      </div>

      {/* Mobile: TOC as bottom sheet */}
      {panel === "toc" && wiki && (
        <div className="fixed inset-x-0 bottom-16 z-30 mx-auto max-w-md rounded-t-xl border bg-card p-4 shadow-2xl lg:hidden">
          <div className="mb-2 flex items-center justify-between">
            <div className="text-sm font-semibold">目录</div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setPanel(null)}
            >
              关闭
            </Button>
          </div>
          <ul className="max-h-64 space-y-1 overflow-auto text-sm">
            {wiki.toc.map((t, i) => (
              <li
                key={`${t.anchor}-${i}`}
                style={{ paddingLeft: `${(t.level - 1) * 12}px` }}
              >
                <a
                  href={`#${t.anchor}`}
                  onClick={() => setPanel(null)}
                  className="block truncate text-muted-foreground hover:text-foreground"
                >
                  {t.text}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}

      {wiki && (
        <GenerateQuestionsDialog
          open={generating}
          wikiId={wiki.id}
          wikiTitle={wiki.title}
          bankQuestionCount={wiki.bank_question_count ?? 0}
          pendingCandidateCount={wiki.pending_candidate_count ?? 0}
          onOpenChange={setGenerating}
        />
      )}

      {wiki && (
        <NewBranchDialog
          open={creatingBranch}
          wikiId={wiki.id}
          branches={branches}
          onOpenChange={setCreatingBranch}
          onCreated={(bid) => setActiveBranchId(bid)}
        />
      )}

      <MergeDialog
        open={merging}
        branch={activeBranch}
        wikiId={wikiId}
        onOpenChange={setMerging}
        onMerged={() => {
          // After merge: refresh main view automatically
          const main = branches.find((b) => b.name === "main");
          if (main) setActiveBranchId(main.id);
        }}
      />
    </>
  );
}
