import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BrainCircuit, Loader2, Play, Save } from "lucide-react";

import {
  reviewScheduleApi,
  type ReviewFrequency,
  type ReviewScheduleUpdate,
} from "@/api/learningNotes";
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

const FREQ_OPTIONS: { value: ReviewFrequency; label: string }[] = [
  { value: "daily", label: "每天" },
  { value: "weekdays", label: "工作日 (周一至周五)" },
  { value: "weekly", label: "每周指定日" },
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

function parseIntervals(text: string): { ok: true; days: number[] } | { ok: false; error: string } {
  const parts = text
    .split(/[,，\s]+/)
    .map((x) => x.trim())
    .filter(Boolean);
  const days: number[] = [];
  for (const p of parts) {
    const n = Number(p);
    if (!Number.isInteger(n) || n < 1 || n > 365) {
      return { ok: false, error: `间隔「${p}」无效，请填 1-365 的整数天` };
    }
    days.push(n);
  }
  if (days.length === 0) return { ok: false, error: "至少填写一个间隔天数" };
  return { ok: true, days: Array.from(new Set(days)).sort((a, b) => a - b) };
}

export function ReviewScheduleSection() {
  const qc = useQueryClient();
  const scheduleQ = useQuery({
    queryKey: ["review-schedule"],
    queryFn: () => reviewScheduleApi.get(),
  });

  const [enabled, setEnabled] = useState(false);
  const [timesText, setTimesText] = useState("08:00");
  const [frequency, setFrequency] = useState<ReviewFrequency>("daily");
  const [weekdays, setWeekdays] = useState<number[]>([]);
  const [intervalsText, setIntervalsText] = useState("1, 3, 7, 15, 30");
  const [maxNotes, setMaxNotes] = useState(5);
  const [masteredFactor, setMasteredFactor] = useState(3);
  const [recallMode, setRecallMode] = useState(true);
  const [feishuEnabled, setFeishuEnabled] = useState(true);

  useEffect(() => {
    if (!scheduleQ.data) return;
    const d = scheduleQ.data;
    setEnabled(d.enabled);
    setTimesText(d.push_times.join(", "));
    setFrequency(d.frequency);
    setWeekdays(d.weekdays);
    setIntervalsText(d.intervals_days.join(", "));
    setMaxNotes(d.max_notes_per_push);
    setMasteredFactor(d.mastered_factor);
    setRecallMode(d.recall_mode);
    setFeishuEnabled(d.feishu_enabled);
  }, [scheduleQ.data]);

  const save = useMutation({
    mutationFn: (body: ReviewScheduleUpdate) => reviewScheduleApi.update(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["review-schedule"] });
      toast.success("复习推送配置已保存");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const trigger = useMutation({
    mutationFn: () => reviewScheduleApi.trigger(),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["review-schedule"] });
      toast.success(res.message);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  function toggleWeekday(d: number) {
    setWeekdays((prev) =>
      prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d].sort(),
    );
  }

  function handleSave() {
    const parsedTimes = parsePushTimesInput(timesText);
    if (!parsedTimes.ok) {
      toast.error(parsedTimes.error);
      return;
    }
    const parsedIntervals = parseIntervals(intervalsText);
    if (!parsedIntervals.ok) {
      toast.error(parsedIntervals.error);
      return;
    }
    save.mutate({
      enabled,
      push_times: parsedTimes.times,
      frequency,
      weekdays: frequency === "weekly" ? weekdays : [],
      intervals_days: parsedIntervals.days,
      max_notes_per_push: maxNotes,
      mastered_factor: masteredFactor,
      recall_mode: recallMode,
      feishu_enabled: feishuEnabled,
    });
  }

  if (scheduleQ.isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        加载复习推送配置…
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
                <BrainCircuit className="h-5 w-5" />
                学习总结复习推送
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                按间隔复习曲线，把到期的学习总结推送到飞书私聊（独立于面试题定时推送）。
              </p>
            </div>
            <label className="flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
                className="h-4 w-4 rounded border"
              />
              启用复习推送
            </label>
          </div>

          <TimezoneHint />

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>推送时间 (HH:MM，多个用逗号分隔)</Label>
              <Input
                value={timesText}
                onChange={(e) => setTimesText(e.target.value)}
                placeholder="08:00"
              />
            </div>
            <div className="space-y-2">
              <Label>频率</Label>
              <Select
                value={frequency}
                onChange={(e) => setFrequency(e.target.value as ReviewFrequency)}
              >
                {FREQ_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-2">
              <Label>间隔复习曲线 (天，逗号分隔)</Label>
              <Input
                value={intervalsText}
                onChange={(e) => setIntervalsText(e.target.value)}
                placeholder="1, 3, 7, 15, 30"
              />
            </div>
            <div className="space-y-2">
              <Label>每次最多推送条数</Label>
              <Input
                type="number"
                min={1}
                max={20}
                value={maxNotes}
                onChange={(e) => setMaxNotes(Number(e.target.value) || 5)}
              />
            </div>
            <div className="space-y-2">
              <Label>已掌握降权倍数</Label>
              <Input
                type="number"
                min={1}
                max={20}
                step={0.5}
                value={masteredFactor}
                onChange={(e) => setMasteredFactor(Number(e.target.value) || 1)}
              />
              <p className="text-xs text-muted-foreground">
                标记已掌握后间隔 ×{masteredFactor || 1}，且排在未掌握之后；填 1 表示不降权。
              </p>
            </div>
            <div className="flex flex-col justify-end gap-2">
              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={recallMode}
                  onChange={(e) => setRecallMode(e.target.checked)}
                  className="h-4 w-4 rounded border"
                />
                主动回忆（先发标题，点「查看要点」再展开）
              </label>
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

          {lastRun || scheduleQ.data?.last_error ? (
            <div className="rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground">
              {lastRun ? <div>上次推送: {lastRun}</div> : null}
              {scheduleQ.data?.last_error ? (
                <div className="text-destructive">
                  上次错误: {scheduleQ.data.last_error}
                </div>
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
            复习节奏由每条总结独立推进：每次推送后自动顺延到下一个间隔；在飞书点「已掌握」不会停推，只是跳到最长间隔再 ×倍数、并排到未掌握之后，「需加强」会回到第一个间隔尽快再推。推送对象受{" "}
            <Badge variant="outline">SL_FEISHU_ALLOWED_OPEN_IDS</Badge> 白名单限制。
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
