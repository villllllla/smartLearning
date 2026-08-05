import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { History, Search, SlidersHorizontal, Trash2, Upload, X } from "lucide-react";

import {
  type Difficulty,
  type QType,
  type QuestionFilter,
  type QuestionSourceKind,
  type QuestionSummary,
  bankApi,
} from "@/api/bank";
import { InterviewImportDialog } from "./InterviewImportDialog";
import { wikiApi } from "@/api/wiki";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Empty } from "@/components/Empty";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/layout/PageHeader";
import { toast } from "@/components/ui/toast";
import { cn, formatDateTime } from "@/lib/utils";
import { difficultyVariant, gradeBadgeVariant, gradeLabel } from "@/lib/grade";
import { SOURCE_KIND_OPTIONS, sourceKindLabel, sourceKindVariant } from "@/lib/sourceKind";

const DIFFICULTIES: Difficulty[] = ["easy", "medium", "hard"];
const QTYPES: QType[] = ["concept", "scenario"];

interface FilterState {
  q: string;
  difficulties: Difficulty[];
  qtypes: QType[];
  source_kinds: QuestionSourceKind[];
  tag_ids: number[];
  tag_mode: "and" | "or";
  source_wiki_ids: number[];
  wrong_only: boolean;
}

const EMPTY_FILTER: FilterState = {
  q: "",
  difficulties: [],
  qtypes: [],
  source_kinds: [],
  tag_ids: [],
  tag_mode: "or",
  source_wiki_ids: [],
  wrong_only: false,
};

export function BankPage() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<FilterState>(EMPTY_FILTER);
  const [showFilters, setShowFilters] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [historyFor, setHistoryFor] = useState<QuestionSummary | null>(null);

  const tagsQ = useQuery({ queryKey: ["bank-tags"], queryFn: () => bankApi.listTags() });
  const wikisQ = useQuery({
    queryKey: ["wiki-list-mini"],
    queryFn: () => wikiApi.list({ limit: 100 }),
  });

  const queryKey = useMemo(() => ["bank-questions", filter] as const, [filter]);
  const { data, isLoading } = useQuery({
    queryKey,
    queryFn: () => {
      const f: QuestionFilter = {
        q: filter.q || undefined,
        difficulties: filter.difficulties.length ? filter.difficulties : undefined,
        qtypes: filter.qtypes.length ? filter.qtypes : undefined,
        source_kinds: filter.source_kinds.length ? filter.source_kinds : undefined,
        tag_ids: filter.tag_ids.length ? filter.tag_ids : undefined,
        tag_mode: filter.tag_ids.length ? filter.tag_mode : undefined,
        source_wiki_ids: filter.source_wiki_ids.length
          ? filter.source_wiki_ids
          : undefined,
        wrong_only: filter.wrong_only || undefined,
        limit: 50,
      };
      return bankApi.listQuestions(f);
    },
  });

  const remove = useMutation({
    mutationFn: (id: number) => bankApi.removeQuestion(id),
    onSuccess: () => {
      toast.success("已删除");
      qc.invalidateQueries({ queryKey: ["bank-questions"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const items = data?.items ?? [];
  const wikiList = wikisQ.data?.items ?? [];
  const tagList = tagsQ.data ?? [];

  const activeFilterCount =
    Number(filter.q !== "") +
    filter.difficulties.length +
    filter.qtypes.length +
    filter.source_kinds.length +
    filter.tag_ids.length +
    filter.source_wiki_ids.length +
    Number(filter.wrong_only);

  return (
    <>
      <PageHeader
        title="题库"
        description={
          isLoading
            ? "加载中..."
            : `共 ${data?.total ?? 0} 道${activeFilterCount > 0 ? ` · 已应用 ${activeFilterCount} 条筛选` : ""}`
        }
        actions={
          <>
            <Button variant="outline" onClick={() => setImportOpen(true)}>
              <Upload className="mr-2 h-4 w-4" />
              导入面经
            </Button>
            <Button variant="outline" asChild>
              <Link to="/bank/candidate-batches">候选批次</Link>
            </Button>
            <Button asChild>
              <Link to="/practice">开始练习</Link>
            </Button>
            <Button
              variant="outline"
              className="md:hidden"
              onClick={() => setShowFilters((s) => !s)}
            >
              <SlidersHorizontal className="h-4 w-4" />
              筛选
            </Button>
          </>
        }
      />

      <div className="mx-auto flex w-full max-w-7xl gap-4 p-4 md:p-8">
        <FilterPanel
          filter={filter}
          tagList={tagList}
          wikiList={wikiList.map((w) => ({ id: w.id, title: w.title }))}
          onChange={setFilter}
          onReset={() => setFilter(EMPTY_FILTER)}
          className={cn("hidden md:block", showFilters && "block")}
        />

        <main className="min-w-0 flex-1 space-y-3">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={filter.q}
              onChange={(e) => setFilter((p) => ({ ...p, q: e.target.value }))}
              placeholder="搜索题干..."
              className="pl-9"
            />
          </div>

          {!isLoading && items.length === 0 && (
            <Empty
              title={activeFilterCount ? "没有匹配的题目" : "题库还是空的"}
              description={
                activeFilterCount
                  ? "试着减少筛选条件"
                  : "到「知识 → 详情 → 生成面试题」生成一批,勾选入库后这里就能看到。"
              }
            />
          )}

          <div className="grid gap-3">
            {items.map((q) => (
              <QuestionCard
                key={q.id}
                q={q}
                onShowHistory={() => setHistoryFor(q)}
                onRemove={() => {
                  if (
                    confirm(`删除题目「${q.question_text.slice(0, 20)}...」?`)
                  ) {
                    remove.mutate(q.id);
                  }
                }}
              />
            ))}
          </div>
        </main>
      </div>

      {historyFor && (
        <HistoryDrawer question={historyFor} onClose={() => setHistoryFor(null)} />
      )}
      <InterviewImportDialog open={importOpen} onOpenChange={setImportOpen} />
    </>
  );
}

// ---------------------------------------------------------------------------
// FilterPanel
// ---------------------------------------------------------------------------

interface FilterPanelProps {
  filter: FilterState;
  tagList: { id: number; name: string }[];
  wikiList: { id: number; title: string }[];
  onChange: (f: FilterState) => void;
  onReset: () => void;
  className?: string;
}

function FilterPanel({
  filter,
  tagList,
  wikiList,
  onChange,
  onReset,
  className,
}: FilterPanelProps) {
  const toggle = <T extends string | number>(arr: T[], v: T): T[] =>
    arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v];

  return (
    <aside
      className={cn(
        "flex max-h-[calc(100dvh-11rem)] w-64 shrink-0 flex-col gap-4 overflow-hidden rounded-xl border bg-card p-4 text-sm",
        className,
      )}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          筛选
        </span>
        <Button variant="ghost" size="sm" onClick={onReset}>
          重置
        </Button>
      </div>

      <FilterGroup label="只看错题">
        <label className="flex cursor-pointer items-center gap-2 text-sm">
          <input
            type="checkbox"
            className="h-4 w-4"
            checked={filter.wrong_only}
            onChange={(e) =>
              onChange({ ...filter, wrong_only: e.target.checked })
            }
          />
          最近一次评级 = C
        </label>
      </FilterGroup>

      <FilterGroup label="难度">
        <div className="flex flex-wrap gap-1.5">
          {DIFFICULTIES.map((d) => (
            <ChipToggle
              key={d}
              label={d}
              active={filter.difficulties.includes(d)}
              onClick={() =>
                onChange({ ...filter, difficulties: toggle(filter.difficulties, d) })
              }
            />
          ))}
        </div>
      </FilterGroup>

      <FilterGroup label="类型">
        <div className="flex flex-wrap gap-1.5">
          {QTYPES.map((t) => (
            <ChipToggle
              key={t}
              label={t === "concept" ? "concept · 八股" : "scenario · 场景"}
              active={filter.qtypes.includes(t)}
              onClick={() =>
                onChange({ ...filter, qtypes: toggle(filter.qtypes, t) })
              }
            />
          ))}
        </div>
      </FilterGroup>

      <FilterGroup label="题目来源">
        <div className="flex flex-wrap gap-1.5">
          {SOURCE_KIND_OPTIONS.map((o) => (
            <ChipToggle
              key={o.value}
              label={o.label}
              active={filter.source_kinds.includes(o.value)}
              onClick={() =>
                onChange({
                  ...filter,
                  source_kinds: toggle(filter.source_kinds, o.value),
                })
              }
            />
          ))}
        </div>
      </FilterGroup>

      <FilterGroup
        label={
          <span className="flex items-center gap-2">
            标签
            {filter.tag_ids.length > 1 && (
              <button
                type="button"
                className="rounded border px-1.5 py-0.5 text-[10px] uppercase text-muted-foreground hover:text-foreground"
                onClick={() =>
                  onChange({
                    ...filter,
                    tag_mode: filter.tag_mode === "or" ? "and" : "or",
                  })
                }
                title="多选标签时:OR=任一命中,AND=全部命中"
              >
                {filter.tag_mode}
              </button>
            )}
          </span>
        }
      >
        {tagList.length === 0 ? (
          <div className="text-xs text-muted-foreground">暂无标签</div>
        ) : (
          <div className="flex max-h-44 flex-wrap gap-1.5 overflow-y-auto">
            {tagList.map((t) => (
              <ChipToggle
                key={t.id}
                label={t.name}
                active={filter.tag_ids.includes(t.id)}
                onClick={() =>
                  onChange({ ...filter, tag_ids: toggle(filter.tag_ids, t.id) })
                }
              />
            ))}
          </div>
        )}
      </FilterGroup>

      <WikiSourceFilter
        wikiList={wikiList}
        selectedIds={filter.source_wiki_ids}
        onChange={(ids) => onChange({ ...filter, source_wiki_ids: ids })}
      />
    </aside>
  );
}

function WikiSourceFilter({
  wikiList,
  selectedIds,
  onChange,
}: {
  wikiList: { id: number; title: string }[];
  selectedIds: number[];
  onChange: (ids: number[]) => void;
}) {
  const [q, setQ] = useState("");

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return wikiList;
    return wikiList.filter(
      (w) =>
        w.title.toLowerCase().includes(needle) || String(w.id).includes(needle),
    );
  }, [wikiList, q]);

  const toggle = (id: number) => {
    onChange(
      selectedIds.includes(id)
        ? selectedIds.filter((x) => x !== id)
        : [...selectedIds, id],
    );
  };

  const selectVisible = () => {
    const visibleIds = filtered.map((w) => w.id);
    onChange([...new Set([...selectedIds, ...visibleIds])]);
  };

  const clearAll = () => onChange([]);

  return (
    <FilterGroup
      label={
        <span className="flex flex-wrap items-center gap-1.5">
          <span>来源 wiki</span>
          {selectedIds.length > 0 && (
            <Badge variant="secondary" className="h-5 px-1.5 text-[10px]">
              已选 {selectedIds.length}
            </Badge>
          )}
          <span className="text-[10px] font-normal text-muted-foreground">
            共 {wikiList.length} 篇
          </span>
        </span>
      }
      className="flex min-h-0 flex-1 flex-col"
    >
      {wikiList.length === 0 ? (
        <div className="text-xs text-muted-foreground">暂无 wiki</div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-2">
          <div className="relative shrink-0">
            <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="搜索 wiki 标题…"
              className="h-8 pl-8 text-xs"
            />
          </div>
          <div className="flex shrink-0 gap-1.5">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 flex-1 text-xs"
              disabled={filtered.length === 0}
              onClick={selectVisible}
            >
              全选当前
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 flex-1 text-xs"
              disabled={selectedIds.length === 0}
              onClick={clearAll}
            >
              清空
            </Button>
          </div>
          <div
            className="min-h-[8rem] flex-1 space-y-0.5 overflow-y-auto rounded-md border bg-muted/20 p-1"
            role="listbox"
            aria-label="来源 wiki 列表"
          >
            {filtered.length === 0 ? (
              <p className="px-2 py-6 text-center text-xs text-muted-foreground">
                无匹配 wiki
              </p>
            ) : (
              filtered.map((w) => {
                const checked = selectedIds.includes(w.id);
                return (
                  <label
                    key={w.id}
                    title={w.title}
                    className={cn(
                      "flex shrink-0 min-h-[2.25rem] cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 text-sm leading-snug transition-colors",
                      checked
                        ? "bg-primary/10 text-foreground"
                        : "hover:bg-muted/60",
                    )}
                  >
                    <input
                      type="checkbox"
                      className="mt-0.5 h-4 w-4 shrink-0 accent-primary"
                      checked={checked}
                      onChange={() => toggle(w.id)}
                    />
                    <span className="min-w-0 flex-1 break-words">{w.title}</span>
                  </label>
                );
              })
            )}
          </div>
        </div>
      )}
    </FilterGroup>
  );
}

function FilterGroup({
  label,
  children,
  className,
}: {
  label: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("shrink-0 space-y-2", className)}>
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      {children}
    </div>
  );
}

function ChipToggle({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full border px-2.5 py-0.5 text-xs transition-colors",
        active
          ? "border-primary bg-primary/10 text-foreground"
          : "border-border text-muted-foreground hover:bg-accent",
      )}
    >
      {label}
    </button>
  );
}

// ---------------------------------------------------------------------------
// QuestionCard
// ---------------------------------------------------------------------------

function QuestionCard({
  q,
  onShowHistory,
  onRemove,
}: {
  q: QuestionSummary;
  onShowHistory: () => void;
  onRemove: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-base font-medium leading-snug">
                {q.question_text}
              </span>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Badge variant={sourceKindVariant(q.source_kind)}>
                {sourceKindLabel(q.source_kind)}
              </Badge>
              {q.source_kind === "interview" && q.interview_answer_status === "pending" ? (
                <Badge variant="outline">答案生成中</Badge>
              ) : null}
              {q.source_kind === "interview" && q.interview_answer_status === "failed" ? (
                <Badge variant="destructive">答案失败</Badge>
              ) : null}
              <Badge variant={difficultyVariant(q.difficulty)}>{q.difficulty}</Badge>
              <Badge variant="outline">{q.qtype}</Badge>
              {q.tags.map((t) => (
                <Badge key={t.id} variant="secondary">
                  {t.name}
                </Badge>
              ))}
              {q.last_grade && (
                <Badge variant={gradeBadgeVariant(q.last_grade)}>
                  最近 {gradeLabel(q.last_grade)}
                </Badge>
              )}
              {q.attempt_count > 0 && (
                <Badge variant="outline">{q.attempt_count} 次作答</Badge>
              )}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <span>入库 {formatDateTime(q.created_at)}</span>
              {q.source_wiki_id && (
                <Link
                  to={`/wiki/${q.source_wiki_id}`}
                  className="text-primary underline-offset-2 hover:underline"
                >
                  → {q.source_wiki_title || `wiki #${q.source_wiki_id}`}
                </Link>
              )}
              {q.last_attempt_at && (
                <span>最近作答 {formatDateTime(q.last_attempt_at)}</span>
              )}
            </div>
            {expanded && (
              <div className="mt-3 whitespace-pre-wrap rounded-md border bg-muted/30 p-3 text-sm leading-relaxed">
                {q.answer_standard || "(无标准答案)"}
              </div>
            )}
            <div className="mt-2 flex flex-wrap gap-2">
              <Button variant="link" size="sm" onClick={() => setExpanded((p) => !p)}>
                {expanded ? "收起答案" : "查看标准答案"}
              </Button>
              {q.attempt_count > 0 && (
                <Button variant="link" size="sm" onClick={onShowHistory}>
                  <History className="h-3.5 w-3.5" />
                  作答历史
                </Button>
              )}
            </div>
          </div>
          <Button variant="ghost" size="icon" aria-label="删除" onClick={onRemove}>
            <Trash2 className="h-4 w-4 text-muted-foreground hover:text-destructive" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// History drawer (right side panel)
// ---------------------------------------------------------------------------

function HistoryDrawer({
  question,
  onClose,
}: {
  question: QuestionSummary;
  onClose: () => void;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["attempts", question.id],
    queryFn: () => bankApi.listAttempts(question.id, 10),
  });
  return (
    <div
      className="fixed inset-0 z-40 flex justify-end bg-black/40"
      onClick={onClose}
    >
      <div
        className="h-full w-full max-w-md overflow-y-auto bg-card p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-start justify-between gap-2">
          <div>
            <div className="text-xs uppercase tracking-wider text-muted-foreground">
              作答历史 · 最近 10 次
            </div>
            <div className="mt-1 text-sm font-medium leading-snug">
              {question.question_text}
            </div>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="关闭">
            <X className="h-4 w-4" />
          </Button>
        </div>
        {isLoading && (
          <div className="text-sm text-muted-foreground">加载中...</div>
        )}
        {data && data.length === 0 && (
          <div className="text-sm text-muted-foreground">暂无作答记录。</div>
        )}
        <div className="space-y-3">
          {(data ?? []).map((a) => (
            <div key={a.id} className="rounded-md border p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={gradeBadgeVariant(a.grade)}>{gradeLabel(a.grade)}</Badge>
                <span className="text-xs text-muted-foreground">
                  {formatDateTime(a.created_at)}
                </span>
              </div>
              <div className="mt-2 grid grid-cols-4 gap-1 text-[10px] uppercase text-muted-foreground">
                <span>正确 {a.score_correctness}</span>
                <span>完整 {a.score_completeness}</span>
                <span>结构 {a.score_structure}</span>
                <span>深度 {a.score_depth}</span>
              </div>
              <div className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
                {a.feedback_text}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
