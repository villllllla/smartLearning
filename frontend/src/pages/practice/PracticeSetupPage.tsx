import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { Play } from "lucide-react";

import { type Difficulty, type QType, type QuestionSourceKind, bankApi } from "@/api/bank";
import { wikiApi } from "@/api/wiki";
import { type PracticeSetupRequest, practiceApi } from "@/api/practice";
import { settingsApi } from "@/api/settings";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/layout/PageHeader";
import { Select } from "@/components/ui/select";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import { SOURCE_KIND_OPTIONS } from "@/lib/sourceKind";
import { setPracticeSession } from "./session";

const DIFFICULTIES: Difficulty[] = ["easy", "medium", "hard"];
const QTYPES: QType[] = ["concept", "scenario"];
const TIME_LIMITS: Array<{ label: string; value: number | null }> = [
  { label: "不限", value: null },
  { label: "30 秒", value: 30 },
  { label: "60 秒", value: 60 },
  { label: "120 秒", value: 120 },
];

export function PracticeSetupPage() {
  const navigate = useNavigate();
  const tagsQ = useQuery({ queryKey: ["bank-tags"], queryFn: () => bankApi.listTags() });
  const wikisQ = useQuery({
    queryKey: ["wiki-list-mini"],
    queryFn: () => wikiApi.list({ limit: 100 }),
  });
  const settingsQ = useQuery({
    queryKey: ["app-settings"],
    queryFn: () => settingsApi.get(),
  });

  const [difficulties, setDifficulties] = useState<Difficulty[]>([]);
  const [qtypes, setQtypes] = useState<QType[]>([]);
  const [sourceKinds, setSourceKinds] = useState<QuestionSourceKind[]>([]);
  const [tagIds, setTagIds] = useState<number[]>([]);
  const [tagMode, setTagMode] = useState<"and" | "or">("or");
  const [sourceWikiIds, setSourceWikiIds] = useState<number[]>([]);
  const [mode, setMode] = useState<"sequential" | "random" | "wrong">("sequential");
  const [limit, setLimit] = useState(10);
  const [timeLimit, setTimeLimit] = useState<number | null>(null);

  // Hydrate defaults from /api/settings exactly once, but only fields the
  // user hasn't started editing (i.e. still at our hard-coded defaults).
  const hydratedRef = useRef(false);
  useEffect(() => {
    if (hydratedRef.current) return;
    if (!settingsQ.data) return;
    hydratedRef.current = true;
    setLimit(settingsQ.data.practice_default_limit);
    setTimeLimit(settingsQ.data.practice_time_limit_per_question);
    if (settingsQ.data.practice_default_difficulties.length > 0) {
      setDifficulties(settingsQ.data.practice_default_difficulties);
    }
    if (settingsQ.data.practice_default_qtypes.length > 0) {
      setQtypes(settingsQ.data.practice_default_qtypes);
    }
  }, [settingsQ.data]);

  const setup = useMutation({
    mutationFn: (req: PracticeSetupRequest) => practiceApi.setup(req),
    onSuccess: (res) => {
      if (res.questions.length === 0) {
        toast.error("题集为空,请放宽筛选条件或先生成题目");
        return;
      }
      setPracticeSession({
        questions: res.questions,
        answers: {},
        timeLimit: res.time_limit_per_question,
        startedAt: Date.now(),
      });
      navigate("/practice/run");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const start = () => {
    setup.mutate({
      difficulties: difficulties.length ? difficulties : undefined,
      qtypes: qtypes.length ? qtypes : undefined,
      source_kinds: sourceKinds.length ? sourceKinds : undefined,
      tag_ids: tagIds.length ? tagIds : undefined,
      tag_mode: tagIds.length ? tagMode : undefined,
      source_wiki_ids: sourceWikiIds.length ? sourceWikiIds : undefined,
      mode,
      limit,
      time_limit_per_question: timeLimit,
    });
  };

  const toggle = <T,>(arr: T[], v: T): T[] =>
    arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v];

  const wikiList = wikisQ.data?.items ?? [];
  const tagList = tagsQ.data ?? [];

  const filterDescription = useMemo(() => {
    const parts: string[] = [];
    if (mode === "wrong") parts.push("仅错题");
    else if (mode === "random") parts.push("随机");
    else parts.push("顺序");
    if (difficulties.length) parts.push(`难度: ${difficulties.join(",")}`);
    if (qtypes.length) parts.push(`类型: ${qtypes.join(",")}`);
    if (sourceKinds.length)
      parts.push(
        `来源: ${sourceKinds.map((k) => SOURCE_KIND_OPTIONS.find((o) => o.value === k)?.label ?? k).join("+")}`,
      );
    if (tagIds.length) parts.push(`标签 x${tagIds.length} (${tagMode.toUpperCase()})`);
    if (sourceWikiIds.length) parts.push(`来源 wiki x${sourceWikiIds.length}`);
    parts.push(`${limit} 题`);
    if (timeLimit) parts.push(`每题 ${timeLimit}s`);
    return parts.join(" · ");
  }, [mode, difficulties, qtypes, sourceKinds, tagIds, tagMode, sourceWikiIds, limit, timeLimit]);

  return (
    <>
      <PageHeader
        title="练习"
        description="组合筛选 → 出题 → 逐题作答 → 立刻拿到 S/A/B/C 评分与改进建议(PRD §6.4)"
      />

      <div className="mx-auto max-w-3xl space-y-4 p-4 md:p-8">
        <Card>
          <CardContent className="space-y-5 p-5">
            <Section title="模式">
              <div className="flex flex-wrap gap-2">
                {(
                  [
                    ["sequential", "顺序"],
                    ["random", "随机"],
                    ["wrong", "错题回顾(最近一次=C)"],
                  ] as const
                ).map(([v, l]) => (
                  <ChipToggle
                    key={v}
                    label={l}
                    active={mode === v}
                    onClick={() => setMode(v)}
                  />
                ))}
              </div>
            </Section>

            <div className="grid gap-4 sm:grid-cols-2">
              <Section title="题量">
                <Input
                  type="number"
                  min={1}
                  max={50}
                  value={limit}
                  onChange={(e) => setLimit(Math.max(1, Math.min(50, Number(e.target.value) || 10)))}
                />
              </Section>
              <Section title="每题时间限制">
                <Select
                  value={String(timeLimit ?? "")}
                  onChange={(e) =>
                    setTimeLimit(e.target.value === "" ? null : Number(e.target.value))
                  }
                >
                  {(() => {
                    const baseValues = TIME_LIMITS.map((t) => t.value);
                    const opts = [...TIME_LIMITS];
                    if (
                      timeLimit !== null &&
                      timeLimit !== undefined &&
                      !baseValues.includes(timeLimit)
                    ) {
                      opts.push({ label: `${timeLimit} 秒（偏好）`, value: timeLimit });
                    }
                    return opts.map((t) => (
                      <option key={String(t.value)} value={t.value === null ? "" : t.value}>
                        {t.label}
                      </option>
                    ));
                  })()}
                </Select>
              </Section>
            </div>

            <Section title="难度(可多选,留空=全部)">
              <div className="flex flex-wrap gap-1.5">
                {DIFFICULTIES.map((d) => (
                  <ChipToggle
                    key={d}
                    label={d}
                    active={difficulties.includes(d)}
                    onClick={() => setDifficulties(toggle(difficulties, d))}
                  />
                ))}
              </div>
            </Section>

            <Section title="类型(可多选,留空=全部)">
              <div className="flex flex-wrap gap-1.5">
                {QTYPES.map((t) => (
                  <ChipToggle
                    key={t}
                    label={t === "concept" ? "concept · 八股" : "scenario · 场景"}
                    active={qtypes.includes(t)}
                    onClick={() => setQtypes(toggle(qtypes, t))}
                  />
                ))}
              </div>
            </Section>

            <Section title="题目来源(可多选,留空=全部)">
              <div className="flex flex-wrap gap-1.5">
                {SOURCE_KIND_OPTIONS.map((o) => (
                  <ChipToggle
                    key={o.value}
                    label={o.label}
                    active={sourceKinds.includes(o.value)}
                    onClick={() => setSourceKinds(toggle(sourceKinds, o.value))}
                  />
                ))}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                实战面经：从面经文档导入；模拟题库：Wiki 文档由模型生成
              </p>
            </Section>

            <Section
              title={
                <span className="flex items-center gap-2">
                  标签(可多选)
                  {tagIds.length > 1 && (
                    <button
                      type="button"
                      className="rounded border px-1.5 py-0.5 text-[10px] uppercase text-muted-foreground hover:text-foreground"
                      onClick={() => setTagMode(tagMode === "or" ? "and" : "or")}
                      title="多选标签时:OR=任一命中,AND=全部命中"
                    >
                      {tagMode}
                    </button>
                  )}
                </span>
              }
            >
              {tagList.length === 0 ? (
                <div className="text-xs text-muted-foreground">
                  暂无标签 · <Link to="/bank" className="text-primary underline">入库后会自动生成</Link>
                </div>
              ) : (
                <div className="flex max-h-44 flex-wrap gap-1.5 overflow-y-auto">
                  {tagList.map((t) => (
                    <ChipToggle
                      key={t.id}
                      label={t.name}
                      active={tagIds.includes(t.id)}
                      onClick={() => setTagIds(toggle(tagIds, t.id))}
                    />
                  ))}
                </div>
              )}
            </Section>

            <Section title="来源 wiki(可多选,留空=全部)">
              {wikiList.length === 0 ? (
                <div className="text-xs text-muted-foreground">
                  暂无 wiki · <Link to="/wiki" className="text-primary underline">先去上传一篇</Link>
                </div>
              ) : (
                <div className="grid max-h-44 gap-1 overflow-y-auto sm:grid-cols-2">
                  {wikiList.map((w) => (
                    <label
                      key={w.id}
                      className="flex cursor-pointer items-center gap-2 truncate text-xs"
                    >
                      <input
                        type="checkbox"
                        className="h-3.5 w-3.5"
                        checked={sourceWikiIds.includes(w.id)}
                        onChange={() => setSourceWikiIds(toggle(sourceWikiIds, w.id))}
                      />
                      <span className="truncate">{w.title}</span>
                    </label>
                  ))}
                </div>
              )}
            </Section>
          </CardContent>
        </Card>

        <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="text-xs text-muted-foreground">{filterDescription}</div>
          <Button onClick={start} disabled={setup.isPending}>
            <Play className="h-4 w-4" />
            {setup.isPending ? "出题中..." : "开始练习"}
          </Button>
        </div>
      </div>
    </>
  );
}

function Section({
  title,
  children,
}: {
  title: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <Label className="text-xs font-medium text-muted-foreground">{title}</Label>
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
        "rounded-full border px-3 py-1 text-xs transition-colors",
        active
          ? "border-primary bg-primary/10 text-foreground"
          : "border-border text-muted-foreground hover:bg-accent",
      )}
    >
      {label}
    </button>
  );
}

// keep referenced exports happy in tooling
export { Badge };
