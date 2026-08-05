import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Loader2, Play, Save } from "lucide-react";

import { todosApi, type TodoCheckUpdate } from "@/api/todos";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { TimezoneHint } from "./TimezoneHint";

export function TodoCheckSection() {
  const qc = useQueryClient();
  const checkQ = useQuery({ queryKey: ["todo-check"], queryFn: () => todosApi.getCheck() });

  const [enabled, setEnabled] = useState(false);
  const [checkTime, setCheckTime] = useState("08:00");
  const [pushTodayPlan, setPushTodayPlan] = useState(true);
  const [feishuEnabled, setFeishuEnabled] = useState(true);

  useEffect(() => {
    if (!checkQ.data) return;
    const d = checkQ.data;
    setEnabled(d.enabled);
    setCheckTime(d.check_time);
    setPushTodayPlan(d.push_today_plan);
    setFeishuEnabled(d.feishu_enabled);
  }, [checkQ.data]);

  const save = useMutation({
    mutationFn: (body: TodoCheckUpdate) => todosApi.updateCheck(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["todo-check"] });
      toast.success("待办计划检测配置已保存");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const trigger = useMutation({
    mutationFn: () => todosApi.triggerCheck(),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["todos"] });
      qc.invalidateQueries({ queryKey: ["todo-calendar"] });
      toast.success(res.message);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (checkQ.isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        加载待办计划检测配置…
      </div>
    );
  }

  const lastRun = checkQ.data?.last_run_at
    ? new Date(checkQ.data.last_run_at).toLocaleString()
    : null;

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="space-y-6 p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 text-lg font-semibold">
                <CalendarClock className="h-5 w-5" />
                每日计划检测
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                每天定时检查当天是否安排了计划：没有计划则飞书提醒你安排；有计划则推送今日待办清单，
                并自动把过期未完成的任务顺延到今天（延期过久会附上激励话语）。
              </p>
            </div>
            <label className="flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
                className="h-4 w-4 rounded border"
              />
              启用每日检测
            </label>
          </div>

          <TimezoneHint />

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>检测时间 (HH:MM)</Label>
              <Input
                type="time"
                value={checkTime}
                onChange={(e) => setCheckTime(e.target.value)}
              />
            </div>
          </div>

          <div className="flex flex-wrap gap-x-6 gap-y-2">
            <label className="flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={pushTodayPlan}
                onChange={(e) => setPushTodayPlan(e.target.checked)}
                className="h-4 w-4 rounded border"
              />
              有计划时也推送今日清单
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

          {lastRun || checkQ.data?.last_error ? (
            <div className="rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground">
              {lastRun ? <div>上次运行: {lastRun}</div> : null}
              {checkQ.data?.last_error ? (
                <div className="text-destructive">上次错误: {checkQ.data.last_error}</div>
              ) : null}
            </div>
          ) : null}

          <div className="flex flex-wrap gap-2">
            <Button
              onClick={() =>
                save.mutate({
                  enabled,
                  check_time: checkTime,
                  push_today_plan: pushTodayPlan,
                  feishu_enabled: feishuEnabled,
                })
              }
              disabled={save.isPending}
            >
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
              立即检测一次
            </Button>
          </div>

          <p className="text-xs text-muted-foreground">
            顺延与检测按账户全局时区在后台每分钟轮询触发。推送对象受{" "}
            <Badge variant="outline">SL_FEISHU_ALLOWED_OPEN_IDS</Badge> 白名单限制。
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
