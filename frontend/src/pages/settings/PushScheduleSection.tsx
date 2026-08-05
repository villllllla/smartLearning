import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Loader2, Play, Save } from "lucide-react";

import { bankApi, type QuestionSourceKind } from "@/api/bank";
import {
  pushScheduleApi,
  type PushFrequency,
  type PushMode,
  type PushScheduleUpdate,
} from "@/api/pushSchedule";
import type { Difficulty, QType } from "@/api/settings";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { toast } from "@/components/ui/toast";
import { parsePushTimesInput } from "@/lib/pushTimes";
import { cn } from "@/lib/utils";
import { TimezoneHint } from "./TimezoneHint";
import { SOURCE_KIND_OPTIONS } from "@/lib/sourceKind";

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
const FREQ_OPTIONS: { value: PushFrequency; label: string }[] = [
  { value: "daily", label: "每天" },
  { value: "weekdays", label: "工作日 (周一至周五)" },
  { value: "weekly", label: "每周指定日" },
];
const MODE_OPTIONS: { value: PushMode; label: string }[] = [
  { value: "random", label: "随机" },
  { value: "sequential", label: "顺序" },
  { value: "wrong", label: "错题" },
];
const WEEKDAYS = [
  { v: 0, label: "一" },
  { v: 1, label: "二" },
  { v: 2, label: "三" },
  { v: 3, label: "四" },
  { v: 4, label: "五" },
  { v: 5, label: "六" },
  { v: 6, label: "日" },
];

export function PushScheduleSection() {
  const qc = useQueryClient();
  const scheduleQ = useQuery({
    queryKey: ["push-schedule"],
    queryFn: () => pushScheduleApi.get(),
  });
  const tagsQ = useQuery({ queryKey: ["bank-tags"], queryFn: () => bankApi.listTags() });

  const [enabled, setEnabled] = useState(false);
  const [timesText, setTimesText] = useState("09:00");
  const [frequency, setFrequency] = useState<PushFrequency>("daily");
  const [weekdays, setWeekdays] = useState<number[]>([]);
  const [limit, setLimit] = useState(3);
  const [mode, setMode] = useState<PushMode>("random");
  const [difficulties, setDifficulties] = useState<Difficulty[]>([]);
  const [qtypes, setQtypes] = useState<QType[]>([]);
  const [tagIds, setTagIds] = useState<number[]>([]);
  const [sourceKinds, setSourceKinds] = useState<QuestionSourceKind[]>([]);
  const [feishuEnabled, setFeishuEnabled] = useState(true);

  useEffect(() => {
    if (!scheduleQ.data) return;
    const d = scheduleQ.data;
    setEnabled(d.enabled);
    setTimesText(d.push_times.join(", "));
    setFrequency(d.frequency);
    setWeekdays(d.weekdays);
    setLimit(d.limit);
    setMode(d.mode);
    setDifficulties(d.difficulties);
    setQtypes(d.qtypes);
    setTagIds(d.tag_ids);
    setSourceKinds((d.source_kinds ?? []) as QuestionSourceKind[]);
    setFeishuEnabled(d.feishu_enabled);
  }, [scheduleQ.data]);

  const save = useMutation({
    mutationFn: (body: PushScheduleUpdate) => pushScheduleApi.update(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["push-schedule"] });
      toast.success("定时推题配置已保存");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const trigger = useMutation({
    mutationFn: () => pushScheduleApi.trigger(),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["push-schedule"] });
      toast.success(res.message);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  function toggleDiff(d: Difficulty) {
    setDifficulties((prev) =>
      prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d],
    );
  }

  function toggleQtype(q: QType) {
    setQtypes((prev) => (prev.includes(q) ? prev.filter((x) => x !== q) : [...prev, q]));
  }

  function toggleWeekday(d: number) {
    setWeekdays((prev) =>
      prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d].sort(),
    );
  }

  function toggleTag(id: number) {
    setTagIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  function toggleSourceKind(k: QuestionSourceKind) {
    setSourceKinds((prev) =>
      prev.includes(k) ? prev.filter((x) => x !== k) : [...prev, k],
    );
  }

  function handleSave() {
    const parsed = parsePushTimesInput(timesText);
    if (!parsed.ok) {
      toast.error(parsed.error);
      return;
    }
    save.mutate({
      enabled,
      push_times: parsed.times,
      frequency,
      weekdays: frequency === "weekly" ? weekdays : [],
      limit,
      mode,
      difficulties,
      qtypes,
      tag_ids: tagIds,
      source_kinds: sourceKinds,
      feishu_enabled: feishuEnabled,
    });
  }

  if (scheduleQ.isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        加载推送配置…
      </div>
    );
  }

  const lastRun = scheduleQ.data?.last_run_at
    ? new Date(scheduleQ.data.last_run_at).toLocaleString()
    : null;

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="space-y-6 p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 text-lg font-semibold">
                <Bell className="h-5 w-5" />
                定时推送面试题
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                按设定时间自动抽题并推送到飞书私聊。也可在飞书说「推送设置」「立即推题」。
              </p>
            </div>
            <label className="flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
                className="h-4 w-4 rounded border"
              />
              启用定时推送
            </label>
          </div>

          <TimezoneHint />

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>推送时间 (HH:MM，多个用逗号分隔)</Label>
              <Input
                value={timesText}
                onChange={(e) => setTimesText(e.target.value)}
                placeholder="09:00, 18:30"
                aria-invalid={timesText.trim() !== "" && !parsePushTimesInput(timesText).ok}
              />
              <p className="text-xs text-muted-foreground">
                仅支持 00:00–23:59，多个时间用英文或中文逗号分隔；无效字符无法保存。
              </p>
            </div>
            <div className="space-y-2">
              <Label>频率</Label>
              <Select
                value={frequency}
                onChange={(e) => setFrequency(e.target.value as PushFrequency)}
              >
                {FREQ_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-2">
              <Label>每次题量</Label>
              <Input
                type="number"
                min={1}
                max={20}
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value) || 3)}
              />
            </div>
            <div className="space-y-2">
              <Label>出题模式</Label>
              <Select value={mode} onChange={(e) => setMode(e.target.value as PushMode)}>
                {MODE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-2 flex items-end">
              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={feishuEnabled}
                  onChange={(e) => setFeishuEnabled(e.target.checked)}
                  className="h-4 w-4 rounded border"
                />
                推送到飞书
              </label>
            </div>
          </div>

          {frequency === "weekly" ? (
            <div className="space-y-2">
              <Label>推送星期</Label>
              <div className="flex flex-wrap gap-2">
                {WEEKDAYS.map((d) => (
                  <button
                    key={d.v}
                    type="button"
                    onClick={() => toggleWeekday(d.v)}
                    className={cn(
                      "rounded-md border px-3 py-1 text-sm",
                      weekdays.includes(d.v)
                        ? "border-primary bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:bg-accent",
                    )}
                  >
                    周{d.label}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          <div className="space-y-2">
            <Label>难度 (不选=不限)</Label>
            <div className="flex flex-wrap gap-2">
              {DIFFICULTIES.map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => toggleDiff(d)}
                  className={cn(
                    "rounded-md border px-3 py-1 text-sm",
                    difficulties.includes(d)
                      ? "border-primary bg-primary/10"
                      : "text-muted-foreground hover:bg-accent",
                  )}
                >
                  {DIFFICULTY_LABEL[d]}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <Label>题型 (不选=不限)</Label>
            <div className="flex flex-wrap gap-2">
              {QTYPES.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => toggleQtype(q)}
                  className={cn(
                    "rounded-md border px-3 py-1 text-sm",
                    qtypes.includes(q)
                      ? "border-primary bg-primary/10"
                      : "text-muted-foreground hover:bg-accent",
                  )}
                >
                  {QTYPE_LABEL[q]}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <Label>题目来源 (不选=不限)</Label>
            <div className="flex flex-wrap gap-2">
              {SOURCE_KIND_OPTIONS.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  title={o.hint}
                  onClick={() => toggleSourceKind(o.value)}
                  className={cn(
                    "rounded-md border px-3 py-1 text-sm",
                    sourceKinds.includes(o.value)
                      ? "border-primary bg-primary/10"
                      : "text-muted-foreground hover:bg-accent",
                  )}
                >
                  {o.label}
                </button>
              ))}
            </div>
          </div>

          {tagsQ.data && tagsQ.data.length > 0 ? (
            <div className="space-y-2">
              <Label>标签 (不选=不限)</Label>
              <div className="flex max-h-32 flex-wrap gap-2 overflow-y-auto">
                {tagsQ.data.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => toggleTag(t.id)}
                    className={cn(
                      "rounded-full border px-2.5 py-0.5 text-xs",
                      tagIds.includes(t.id)
                        ? "border-primary bg-primary/10"
                        : "text-muted-foreground hover:bg-accent",
                    )}
                  >
                    {t.name}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {lastRun || scheduleQ.data?.last_error ? (
            <div className="rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground">
              {lastRun ? <div>上次推送: {lastRun}</div> : null}
              {scheduleQ.data?.last_error ? (
                <div className="text-destructive">上次错误: {scheduleQ.data.last_error}</div>
              ) : null}
            </div>
          ) : null}

          <div className="flex flex-wrap gap-2">
            <Button onClick={handleSave} disabled={save.isPending}>
              {save.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Save className="mr-2 h-4 w-4" />
              )}
              保存配置
            </Button>
            <Button
              variant="outline"
              onClick={() => trigger.mutate()}
              disabled={trigger.isPending}
            >
              {trigger.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Play className="mr-2 h-4 w-4" />
              )}
              立即推送
            </Button>
          </div>

          <p className="text-xs text-muted-foreground">
            飞书用户需至少私聊机器人一次以建立会话；推送对象受{" "}
            <Badge variant="outline">SL_FEISHU_ALLOWED_OPEN_IDS</Badge> 白名单限制。
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
