/**
 * Settings → 数据与外观 (PRD §6.5).
 *
 * - Reads/writes /api/settings (rolling history N, default practice limit/time/
 *   difficulties/types, theme).
 * - Exports bank as JSON / CSV; exports wikis as zip.
 * - Clears scoped data (chats / attempts / candidates / questions / all) with
 *   a typed-confirmation guard for the destructive scopes.
 */
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  BookOpen,
  Download,
  FolderSync,
  GitMerge,
  Loader2,
  Monitor,
  Moon,
  Save,
  Sun,
  Trash2,
} from "lucide-react";

import { bankApi, type DedupePreview } from "@/api/bank";
import { dataApi, type ClearScope } from "@/api/data";
import { obsidianSyncApi } from "@/api/obsidianSync";
import { ragApi } from "@/api/rag";
import { RagChunksPanel } from "@/components/RagChunksPanel";
import { settingsApi, type Difficulty, type QType } from "@/api/settings";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import { useTheme, type Theme } from "@/lib/theme";

const DIFFICULTIES: Difficulty[] = ["easy", "medium", "hard"];
const QTYPES: QType[] = ["concept", "scenario"];
const DIFFICULTY_LABEL: Record<Difficulty, string> = {
  easy: "简单",
  medium: "中等",
  hard: "困难",
};
const QTYPE_LABEL: Record<QType, string> = {
  concept: "概念",
  scenario: "场景",
};

const SCOPE_META: Record<
  ClearScope,
  { label: string; description: string; danger: boolean }
> = {
  chats: {
    label: "对话记录",
    description: "删除全部 Chat 会话与消息（不影响已生成的题/作答）",
    danger: false,
  },
  attempts: {
    label: "作答历史",
    description: "清空所有作答记录与评分痕迹",
    danger: false,
  },
  candidates: {
    label: "候选题",
    description: "丢弃所有未提交的候选题批次",
    danger: false,
  },
  questions: {
    label: "题库",
    description: "清空全部题目与标签（评分依赖的标准答案也会丢失，慎用）",
    danger: true,
  },
  all: {
    label: "全部业务数据",
    description:
      "清空 Chat / 候选题 / 题目 / 作答；保留模型、Provider、Prompt、Wiki 与本页设置",
    danger: true,
  },
};

export function DataAppearanceSection() {
  const qc = useQueryClient();
  const { theme: localTheme, setTheme: setLocalTheme } = useTheme();
  const settingsQ = useQuery({
    queryKey: ["app-settings"],
    queryFn: () => settingsApi.get(),
  });

  // Local form state mirrors fetched settings until saved.
  const [dedupeThreshold, setDedupeThreshold] = useState(0.85);
  const [dedupePreview, setDedupePreview] = useState<DedupePreview | null>(null);

  const ragStatus = useQuery({
    queryKey: ["rag-status"],
    queryFn: () => ragApi.status(),
  });

  const ragRebuild = useMutation({
    mutationFn: () => ragApi.rebuild(),
    onSuccess: (res) => {
      toast.success(
        `RAG 索引：${res.wikis_processed} 篇 Wiki，${res.chunks_written} 个片段`,
      );
      void qc.invalidateQueries({ queryKey: ["rag-status"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const obsidianStatus = useQuery({
    queryKey: ["obsidian-sync-status"],
    queryFn: () => obsidianSyncApi.status(),
    refetchInterval: 30_000,
  });

  const [form, setForm] = useState<{
    practice_default_limit: number;
    practice_time_limit_per_question: number | null;
    practice_default_difficulties: Difficulty[];
    practice_default_qtypes: QType[];
    practice_history_keep_n: number;
    appearance_theme: Theme;
  } | null>(null);

  useEffect(() => {
    if (!settingsQ.data) return;
    setForm({
      practice_default_limit: settingsQ.data.practice_default_limit,
      practice_time_limit_per_question:
        settingsQ.data.practice_time_limit_per_question,
      practice_default_difficulties:
        settingsQ.data.practice_default_difficulties,
      practice_default_qtypes: settingsQ.data.practice_default_qtypes,
      practice_history_keep_n: settingsQ.data.practice_history_keep_n,
      appearance_theme: settingsQ.data.appearance_theme,
    });
  }, [settingsQ.data]);

  const obsidianScan = useMutation({
    mutationFn: (force: boolean) => obsidianSyncApi.scan(force),
    onSuccess: (res) => {
      const repaired =
        res.wikis_repaired != null && res.wikis_repaired > 0
          ? `，修复分支 ${res.wikis_repaired}`
          : "";
      const failed = res.failed > 0 ? `，失败 ${res.failed}` : "";
      toast.success(
        `同步完成：扫描 ${res.scanned}，新建 ${res.created}，更新 ${res.updated}，跳过 ${res.skipped}${repaired}${failed}`,
      );
      void qc.invalidateQueries({ queryKey: ["obsidian-sync-status"] });
      void qc.invalidateQueries({ queryKey: ["wiki-list"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const scanDedupe = useMutation({
    mutationFn: () => bankApi.dedupePreview({ threshold: dedupeThreshold }),
    onSuccess: (data) => {
      setDedupePreview(data);
      if (data.cluster_count === 0) {
        toast.success(`未发现相似题重复（${data.method === "embedding" ? "语义" : "字符串"}模式）`);
      } else {
        toast.success(
          `发现 ${data.cluster_count} 组重复，可合并 ${data.duplicate_question_count} 道题（${data.method === "embedding" ? "语义" : "字符串"}）`,
        );
      }
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const backfillEmbeddings = useMutation({
    mutationFn: () => bankApi.dedupeBackfillEmbeddings(),
    onSuccess: (res) => {
      toast.success(
        `向量补全完成：共 ${res.total_questions} 道题，新计算 ${res.newly_embedded} 道`,
      );
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const mergeDedupe = useMutation({
    mutationFn: () =>
      bankApi.dedupeMerge({ threshold: dedupeThreshold, dry_run: false }),
    onSuccess: (res) => {
      toast.success(
        `已合并 ${res.clusters_merged} 组，移除 ${res.questions_removed} 道重复题，迁移 ${res.attempts_reassigned} 条作答记录`,
      );
      setDedupePreview(null);
      void qc.invalidateQueries({ queryKey: ["bank-questions"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const save = useMutation({
    mutationFn: () => {
      if (!form) return Promise.reject(new Error("未加载"));
      return settingsApi.update({
        practice_default_limit: form.practice_default_limit,
        practice_time_limit_per_question:
          form.practice_time_limit_per_question === null
            ? undefined
            : form.practice_time_limit_per_question,
        clear_time_limit: form.practice_time_limit_per_question === null,
        practice_default_difficulties: form.practice_default_difficulties,
        practice_default_qtypes: form.practice_default_qtypes,
        practice_history_keep_n: form.practice_history_keep_n,
        appearance_theme: form.appearance_theme,
      });
    },
    onSuccess: (data) => {
      toast.success("设置已保存");
      qc.setQueryData(["app-settings"], data);
      // Apply theme to UI immediately
      setLocalTheme(data.appearance_theme);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const exportBank = useMutation({
    mutationFn: (fmt: "json" | "csv") => dataApi.exportBank(fmt),
    onError: (e: Error) => toast.error(e.message),
  });
  const exportWikis = useMutation({
    mutationFn: () => dataApi.exportWikis(),
    onError: (e: Error) => toast.error(e.message),
  });

  const [clearScope, setClearScope] = useState<ClearScope | null>(null);
  const [confirmText, setConfirmText] = useState("");
  const clearMut = useMutation({
    mutationFn: (scope: ClearScope) => dataApi.clear(scope),
    onSuccess: (data, scope) => {
      const total = Object.values(data.deleted).reduce((a, b) => a + b, 0);
      toast.success(`${SCOPE_META[scope].label} 已清空（共 ${total} 条）`);
      // Invalidate everything queryable that may have changed
      qc.invalidateQueries();
      setClearScope(null);
      setConfirmText("");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (settingsQ.isLoading || !form) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-muted-foreground">
          <Loader2 className="mx-auto mb-2 h-5 w-5 animate-spin" />
          加载中…
        </CardContent>
      </Card>
    );
  }

  const toggleInArray = <T,>(arr: T[], item: T): T[] =>
    arr.includes(item) ? arr.filter((x) => x !== item) : [...arr, item];

  return (
    <div className="space-y-6">
      {/* ───────── Appearance ───────── */}
      <Card>
        <CardContent className="space-y-4 p-6">
          <div>
            <h3 className="text-base font-semibold">外观</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              主题立即应用到当前浏览器；保存后跨设备复用同一偏好。
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            {(
              [
                { value: "light", label: "浅色", Icon: Sun },
                { value: "dark", label: "深色", Icon: Moon },
                { value: "system", label: "跟随系统", Icon: Monitor },
              ] as const
            ).map(({ value, label, Icon }) => {
              const active = form.appearance_theme === value;
              return (
                <button
                  key={value}
                  type="button"
                  onClick={() => {
                    setForm({ ...form, appearance_theme: value });
                    setLocalTheme(value);
                  }}
                  className={cn(
                    "flex items-center gap-2 rounded-md border px-4 py-2 text-sm transition-colors",
                    active
                      ? "border-primary bg-primary/10 text-foreground"
                      : "border-border text-muted-foreground hover:bg-muted",
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {label}
                </button>
              );
            })}
            <span className="ml-auto self-center text-xs text-muted-foreground">
              当前：{localTheme === "system" ? "跟随系统" : localTheme === "dark" ? "深色" : "浅色"}
            </span>
          </div>
        </CardContent>
      </Card>

      {/* ───────── Practice defaults ───────── */}
      <Card>
        <CardContent className="space-y-5 p-6">
          <div>
            <h3 className="text-base font-semibold">练习偏好</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              用于「练习设置」页的默认值；评分服务也会按「保留历史 N」滚动裁剪老记录。
            </p>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="default-limit">默认题量</Label>
              <Input
                id="default-limit"
                type="number"
                min={1}
                max={50}
                value={form.practice_default_limit}
                onChange={(e) =>
                  setForm({
                    ...form,
                    practice_default_limit: Math.max(
                      1,
                      Math.min(50, parseInt(e.target.value || "1", 10)),
                    ),
                  })
                }
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="time-limit">单题时间（秒）</Label>
              <div className="flex items-center gap-2">
                <Input
                  id="time-limit"
                  type="number"
                  min={10}
                  max={600}
                  placeholder="不限"
                  value={form.practice_time_limit_per_question ?? ""}
                  onChange={(e) => {
                    const v = e.target.value;
                    setForm({
                      ...form,
                      practice_time_limit_per_question:
                        v === "" ? null : Math.max(10, Math.min(600, parseInt(v, 10))),
                    });
                  }}
                />
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    setForm({
                      ...form,
                      practice_time_limit_per_question: null,
                    })
                  }
                >
                  不限
                </Button>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="keep-n">保留历史次数</Label>
              <Input
                id="keep-n"
                type="number"
                min={1}
                max={200}
                value={form.practice_history_keep_n}
                onChange={(e) =>
                  setForm({
                    ...form,
                    practice_history_keep_n: Math.max(
                      1,
                      Math.min(200, parseInt(e.target.value || "1", 10)),
                    ),
                  })
                }
              />
              <p className="text-[11px] text-muted-foreground">
                每题最多保留最近 N 条作答记录；多余的会在评分写入后自动删除。
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>默认难度</Label>
              <div className="flex flex-wrap gap-2">
                {DIFFICULTIES.map((d) => {
                  const active = form.practice_default_difficulties.includes(d);
                  return (
                    <button
                      key={d}
                      type="button"
                      onClick={() =>
                        setForm({
                          ...form,
                          practice_default_difficulties: toggleInArray(
                            form.practice_default_difficulties,
                            d,
                          ),
                        })
                      }
                      className={cn(
                        "rounded-md border px-3 py-1.5 text-xs transition-colors",
                        active
                          ? "border-primary bg-primary/10 text-foreground"
                          : "border-border text-muted-foreground hover:bg-muted",
                      )}
                    >
                      {DIFFICULTY_LABEL[d]}
                    </button>
                  );
                })}
              </div>
              <p className="text-[11px] text-muted-foreground">
                空 = 不预选，由用户在练习设置页临时勾选。
              </p>
            </div>

            <div className="space-y-2">
              <Label>默认题型</Label>
              <div className="flex flex-wrap gap-2">
                {QTYPES.map((q) => {
                  const active = form.practice_default_qtypes.includes(q);
                  return (
                    <button
                      key={q}
                      type="button"
                      onClick={() =>
                        setForm({
                          ...form,
                          practice_default_qtypes: toggleInArray(
                            form.practice_default_qtypes,
                            q,
                          ),
                        })
                      }
                      className={cn(
                        "rounded-md border px-3 py-1.5 text-xs transition-colors",
                        active
                          ? "border-primary bg-primary/10 text-foreground"
                          : "border-border text-muted-foreground hover:bg-muted",
                      )}
                    >
                      {QTYPE_LABEL[q]}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          <div className="flex justify-end">
            <Button
              onClick={() => save.mutate()}
              disabled={save.isPending}
              className="gap-2"
            >
              {save.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              保存设置
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* ───────── Wiki RAG ───────── */}
      <Card>
        <CardContent className="space-y-4 p-6">
          <div>
            <h3 className="text-base font-semibold">Wiki 知识库 RAG</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              使用 <code className="rounded bg-muted px-1">BAAI/bge-small-zh-v1.5</code>{" "}
              对 Wiki 分块向量化。对话勾选「使用 Wiki 知识库」后，检索相关片段注入模型，并在回复下展示
              <code className="mx-1 rounded bg-muted px-1">/wiki/&lt;id&gt;</code> 链接。
              需先 <code className="rounded bg-muted px-1">pip install -e &quot;.[rag]&quot;</code>{" "}
              并执行 <code className="rounded bg-muted px-1">alembic upgrade head</code>。
            </p>
          </div>
          {ragStatus.data && (
            <p className="text-xs text-muted-foreground">
              模型 {ragStatus.data.embedding_model} · 已索引 {ragStatus.data.wiki_count_indexed}{" "}
              篇 · {ragStatus.data.chunk_count} 个片段
            </p>
          )}
          <Button
            variant="outline"
            className="gap-2"
            disabled={ragRebuild.isPending}
            onClick={() => ragRebuild.mutate()}
          >
            {ragRebuild.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <BookOpen className="h-4 w-4" />
            )}
            重建全部 Wiki 向量索引
          </Button>
          <RagChunksPanel />
        </CardContent>
      </Card>

      {/* ───────── Obsidian sync ───────── */}
      <Card>
        <CardContent className="space-y-4 p-6">
          <div>
            <h3 className="text-base font-semibold">Obsidian 文件夹同步</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              在 <code className="rounded bg-muted px-1">backend/.env</code> 配置{" "}
              <code className="rounded bg-muted px-1">SL_OBSIDIAN_VAULT_PATH</code>{" "}
              与 <code className="rounded bg-muted px-1">SL_OBSIDIAN_SYNC_ENABLED=true</code>
              ，并另开终端运行{" "}
              <code className="rounded bg-muted px-1">python scripts/obsidian_sync_worker.py</code>{" "}
              监听变更；也可在此手动全量扫描。
            </p>
          </div>
          {obsidianStatus.data && (
            <ul className="space-y-1 text-xs text-muted-foreground">
              <li>
                状态：{obsidianStatus.data.enabled ? "已启用" : "未启用"} · 路径：{" "}
                {obsidianStatus.data.vault_path || "(未配置)"}
                {obsidianStatus.data.vault_exists ? "" : " · 路径无效"}
              </li>
              <li>已映射 {obsidianStatus.data.mapped_files} 个 Markdown 文件</li>
              {obsidianStatus.data.last_full_scan_at && (
                <li>上次全量扫描：{obsidianStatus.data.last_full_scan_at}</li>
              )}
            </ul>
          )}
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              className="gap-2"
              disabled={obsidianScan.isPending}
              onClick={() => obsidianScan.mutate(false)}
            >
              {obsidianScan.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <FolderSync className="h-4 w-4" />
              )}
              立即全量同步
            </Button>
            <Button
              variant="outline"
              disabled={obsidianScan.isPending}
              onClick={() => obsidianScan.mutate(true)}
            >
              强制重新导入
            </Button>
          </div>
          {obsidianStatus.data?.recent_events?.length ? (
            <div className="max-h-32 overflow-y-auto rounded-md border border-border p-2 font-mono text-[10px] text-muted-foreground">
              {obsidianStatus.data.recent_events.map((line, i) => (
                <div key={i}>{line}</div>
              ))}
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* ───────── Question dedupe ───────── */}
      <Card>
        <CardContent className="space-y-4 p-6">
          <div>
            <h3 className="text-base font-semibold">相似题归并</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              开启 <code className="text-[11px]">SL_DEDUPE_USE_EMBEDDING=true</code> 后使用
              Embedding 语义相似度（默认 ≥0.92）；否则使用题干字符串相似度（≥0.85）。
              入库时也会自动跳过与已有题过于相似的候选。可选 Milvus 加速检索。
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <div className="grid gap-1">
              <Label htmlFor="dedupe-threshold" className="text-xs">
                相似度阈值
              </Label>
              <Input
                id="dedupe-threshold"
                type="number"
                min={0.5}
                max={1}
                step={0.01}
                className="w-28"
                value={dedupeThreshold}
                onChange={(e) =>
                  setDedupeThreshold(Number.parseFloat(e.target.value) || 0.85)
                }
              />
            </div>
            <Button
              variant="outline"
              className="gap-2"
              onClick={() => scanDedupe.mutate()}
              disabled={scanDedupe.isPending}
            >
              {scanDedupe.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <GitMerge className="h-4 w-4" />
              )}
              扫描重复
            </Button>
            <Button
              variant="outline"
              className="gap-2"
              onClick={() => backfillEmbeddings.mutate()}
              disabled={backfillEmbeddings.isPending}
            >
              {backfillEmbeddings.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : null}
              补全向量
            </Button>
            <Button
              className="gap-2"
              disabled={
                !dedupePreview?.cluster_count || mergeDedupe.isPending
              }
              onClick={() => {
                if (
                  !confirm(
                    `确认合并 ${dedupePreview?.duplicate_question_count ?? 0} 道重复题？作答历史会并入保留题。`,
                  )
                ) {
                  return;
                }
                mergeDedupe.mutate();
              }}
            >
              {mergeDedupe.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <GitMerge className="h-4 w-4" />
              )}
              执行归并
            </Button>
          </div>
          {dedupePreview && dedupePreview.cluster_count > 0 && (
            <div className="max-h-48 space-y-2 overflow-y-auto rounded-md border border-border p-3 text-xs">
              <p className="text-muted-foreground">
                模式：{dedupePreview.method === "embedding" ? "Embedding 语义" : "字符串"} ·
                阈值 {dedupePreview.threshold}
              </p>
              {dedupePreview.clusters.slice(0, 8).map((c) => (
                <div key={c.canonical_id}>
                  <p className="font-medium text-foreground">
                    保留 #{c.canonical_id}：{c.canonical_text.slice(0, 60)}
                    {c.canonical_text.length > 60 ? "…" : ""}
                  </p>
                  <p className="text-muted-foreground">
                    合并：{" "}
                    {c.members
                      .filter((m) => m.id !== c.canonical_id)
                      .map((m) => `#${m.id}`)
                      .join("、")}
                  </p>
                </div>
              ))}
              {dedupePreview.cluster_count > 8 && (
                <p className="text-muted-foreground">
                  另有 {dedupePreview.cluster_count - 8} 组未展开…
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ───────── Export ───────── */}
      <Card>
        <CardContent className="space-y-4 p-6">
          <div>
            <h3 className="text-base font-semibold">导出</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              JSON 包含完整字段（含标签 / 来源 wiki / 冻结的 prompt 和 model
              ID），CSV 用于 Excel 浏览，wiki 包导出 Markdown 与提交历史。
            </p>
          </div>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <Button
              variant="outline"
              className="gap-2"
              onClick={() => exportBank.mutate("json")}
              disabled={exportBank.isPending}
            >
              <Download className="h-4 w-4" />
              导出题库 JSON
            </Button>
            <Button
              variant="outline"
              className="gap-2"
              onClick={() => exportBank.mutate("csv")}
              disabled={exportBank.isPending}
            >
              <Download className="h-4 w-4" />
              导出题库 CSV
            </Button>
            <Button
              variant="outline"
              className="gap-2"
              onClick={() => exportWikis.mutate()}
              disabled={exportWikis.isPending}
            >
              <Download className="h-4 w-4" />
              导出 Wiki 包 (zip)
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* ───────── Clear ───────── */}
      <Card className="border-destructive/30">
        <CardContent className="space-y-4 p-6">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-destructive" />
            <h3 className="text-base font-semibold text-destructive">
              危险区
            </h3>
          </div>
          <p className="text-xs text-muted-foreground">
            清理操作不可逆。删除「题库」会失去所有评分依赖的标准答案；删除「全部业务数据」会保留模型 / Prompt /
            Wiki 与本页设置。
          </p>

          <div className="space-y-3">
            {(Object.keys(SCOPE_META) as ClearScope[]).map((scope) => {
              const meta = SCOPE_META[scope];
              return (
                <div
                  key={scope}
                  className="flex items-center justify-between gap-3 rounded-md border border-border px-4 py-3"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{meta.label}</span>
                      {meta.danger && (
                        <Badge variant="destructive" className="text-[10px]">
                          高风险
                        </Badge>
                      )}
                    </div>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {meta.description}
                    </p>
                  </div>
                  <Button
                    variant={meta.danger ? "destructive" : "outline"}
                    size="sm"
                    className="shrink-0 gap-1.5"
                    onClick={() => {
                      if (meta.danger) {
                        setClearScope(scope);
                        setConfirmText("");
                      } else {
                        clearMut.mutate(scope);
                      }
                    }}
                    disabled={clearMut.isPending}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    清空
                  </Button>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Typed-confirmation modal for destructive scopes */}
      {clearScope && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={() => !clearMut.isPending && setClearScope(null)}
        >
          <div
            className="w-full max-w-md rounded-lg border border-border bg-background p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-destructive" />
              <h4 className="text-base font-semibold">
                确认清空：{SCOPE_META[clearScope].label}
              </h4>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">
              {SCOPE_META[clearScope].description}
            </p>
            <p className="mt-3 text-xs text-muted-foreground">
              请输入 <code className="mx-1 rounded bg-muted px-1.5 py-0.5">DELETE</code>{" "}
              以确认操作。
            </p>
            <Input
              autoFocus
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder="DELETE"
              className="mt-2"
            />
            <div className="mt-4 flex justify-end gap-2">
              <Button
                variant="outline"
                onClick={() => setClearScope(null)}
                disabled={clearMut.isPending}
              >
                取消
              </Button>
              <Button
                variant="destructive"
                disabled={confirmText !== "DELETE" || clearMut.isPending}
                onClick={() => clearMut.mutate(clearScope)}
              >
                {clearMut.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : null}
                确认清空
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Hint about thresholds */}
      <Card>
        <CardContent className="space-y-1 p-6 text-xs text-muted-foreground">
          <p>
            评级阈值 (S/A/B/C) 与生成默认值集中放在
            <code className="mx-1 rounded bg-muted px-1 py-0.5">
              backend/app/prompts/defaults.py
            </code>
            ，改后无需迁移即可生效。
          </p>
          <p>
            外观主题保存到 <code className="mx-1 rounded bg-muted px-1 py-0.5">localStorage</code>
            ，下次打开会先按本地值渲染、再与服务端偏好同步，避免初次闪烁。
          </p>
        </CardContent>
      </Card>

    </div>
  );
}
