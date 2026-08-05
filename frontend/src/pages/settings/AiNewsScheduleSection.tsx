import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Newspaper, Play, Save } from "lucide-react";

import {
  aiNewsApi,
  type AiNewsScheduleUpdate,
  type NewsFrequency,
  type RssFeed,
} from "@/api/aiNews";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/components/ui/toast";
import { parsePushTimesInput } from "@/lib/pushTimes";
import { cn } from "@/lib/utils";
import { TimezoneHint } from "./TimezoneHint";

const FREQ_OPTIONS: { value: NewsFrequency; label: string }[] = [
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

function feedsToText(feeds: RssFeed[]): string {
  return feeds.map((f) => `${f.name} | ${f.url}`).join("\n");
}

function parseFeeds(text: string): RssFeed[] {
  const out: RssFeed[] = [];
  for (const line of text.split("\n")) {
    const s = line.trim();
    if (!s) continue;
    const idx = s.indexOf("|");
    if (idx >= 0) {
      const name = s.slice(0, idx).trim();
      const url = s.slice(idx + 1).trim();
      if (url) out.push({ name: name || url, url });
    } else if (s.startsWith("http")) {
      out.push({ name: s, url: s });
    }
  }
  return out;
}

export function AiNewsScheduleSection() {
  const qc = useQueryClient();
  const scheduleQ = useQuery({
    queryKey: ["ai-news-schedule"],
    queryFn: () => aiNewsApi.getSchedule(),
  });

  const [enabled, setEnabled] = useState(false);
  const [timesText, setTimesText] = useState("09:00");
  const [frequency, setFrequency] = useState<NewsFrequency>("daily");
  const [weekdays, setWeekdays] = useState<number[]>([]);
  const [topN, setTopN] = useState(5);
  const [enableHn, setEnableHn] = useState(true);
  const [enableGh, setEnableGh] = useState(true);
  const [enableArxiv, setEnableArxiv] = useState(true);
  const [enableHf, setEnableHf] = useState(true);
  const [enableReddit, setEnableReddit] = useState(true);
  const [feedsText, setFeedsText] = useState("");
  const [dedupDays, setDedupDays] = useState(7);
  const [feishuEnabled, setFeishuEnabled] = useState(true);

  useEffect(() => {
    if (!scheduleQ.data) return;
    const d = scheduleQ.data;
    setEnabled(d.enabled);
    setTimesText(d.push_times.join(", "));
    setFrequency(d.frequency);
    setWeekdays(d.weekdays);
    setTopN(d.top_n);
    setEnableHn(d.enable_hackernews);
    setEnableGh(d.enable_github);
    setEnableArxiv(d.enable_arxiv);
    setEnableHf(d.enable_huggingface);
    setEnableReddit(d.enable_reddit);
    setFeedsText(feedsToText(d.rss_feeds));
    setDedupDays(d.dedup_days);
    setFeishuEnabled(d.feishu_enabled);
  }, [scheduleQ.data]);

  const save = useMutation({
    mutationFn: (body: AiNewsScheduleUpdate) => aiNewsApi.updateSchedule(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ai-news-schedule"] });
      toast.success("AI 资讯推送配置已保存");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const trigger = useMutation({
    mutationFn: () => aiNewsApi.trigger(),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["ai-news-schedule"] });
      qc.invalidateQueries({ queryKey: ["ai-news"] });
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
    const anySource =
      enableHn ||
      enableGh ||
      enableArxiv ||
      enableHf ||
      enableReddit ||
      parseFeeds(feedsText).length > 0;
    if (!anySource) {
      toast.error("至少启用一个来源");
      return;
    }
    save.mutate({
      enabled,
      push_times: parsedTimes.times,
      frequency,
      weekdays: frequency === "weekly" ? weekdays : [],
      top_n: topN,
      enable_hackernews: enableHn,
      enable_github: enableGh,
      enable_arxiv: enableArxiv,
      enable_huggingface: enableHf,
      enable_reddit: enableReddit,
      rss_feeds: parseFeeds(feedsText),
      dedup_days: dedupDays,
      feishu_enabled: feishuEnabled,
    });
  }

  if (scheduleQ.isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        加载 AI 资讯推送配置…
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
                <Newspaper className="h-5 w-5" />
                AI 资讯每日推送
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                每日抓取 HackerNews / GitHub Trending / 中文 RSS，模型去重排序后把热点
                Top N（含出处、链接）推送到飞书私聊。
              </p>
            </div>
            <label className="flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
                className="h-4 w-4 rounded border"
              />
              启用资讯推送
            </label>
          </div>

          <TimezoneHint />

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>推送时间 (HH:MM，多个用逗号分隔)</Label>
              <Input
                value={timesText}
                onChange={(e) => setTimesText(e.target.value)}
                placeholder="09:00"
              />
            </div>
            <div className="space-y-2">
              <Label>频率</Label>
              <Select
                value={frequency}
                onChange={(e) => setFrequency(e.target.value as NewsFrequency)}
              >
                {FREQ_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-2">
              <Label>每次推送条数 (Top N)</Label>
              <Input
                type="number"
                min={1}
                max={15}
                value={topN}
                onChange={(e) => setTopN(Number(e.target.value) || 5)}
              />
            </div>
            <div className="space-y-2">
              <Label>去重天数（跳过近 N 天已推过的链接）</Label>
              <Input
                type="number"
                min={0}
                max={90}
                value={dedupDays}
                onChange={(e) => setDedupDays(Number(e.target.value) || 0)}
              />
            </div>
            <div className="flex flex-col justify-end gap-2">
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

          <div className="space-y-2">
            <Label>抓取来源</Label>
            <div className="flex flex-wrap gap-x-6 gap-y-2">
              {(
                [
                  ["Hacker News", enableHn, setEnableHn],
                  ["GitHub Trending", enableGh, setEnableGh],
                  ["arXiv (cs.AI/LG/CL/CV)", enableArxiv, setEnableArxiv],
                  ["HuggingFace Papers", enableHf, setEnableHf],
                  ["Reddit (LocalLLaMA/ML)", enableReddit, setEnableReddit],
                ] as [string, boolean, (v: boolean) => void][]
              ).map(([label, checked, setter]) => (
                <label
                  key={label}
                  className="flex cursor-pointer items-center gap-2 text-sm"
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(e) => setter(e.target.checked)}
                    className="h-4 w-4 rounded border"
                  />
                  {label}
                </label>
              ))}
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
            <Label>中文 RSS 源（每行一个，格式：名称 | 链接；留空用默认量子位）</Label>
            <Textarea
              value={feedsText}
              onChange={(e) => setFeedsText(e.target.value)}
              placeholder={"量子位 | https://www.qbitai.com/feed"}
              rows={3}
            />
          </div>

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
              立即抓取推送
            </Button>
          </div>

          <p className="text-xs text-muted-foreground">
            抓取走系统代理，海外源与 LLM 同一链路。链接与出处均来自真实抓取，模型只做去重/排序/中文摘要。推送对象受{" "}
            <Badge variant="outline">SL_FEISHU_ALLOWED_OPEN_IDS</Badge> 白名单限制。
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
