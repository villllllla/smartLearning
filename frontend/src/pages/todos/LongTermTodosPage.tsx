import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CalendarRange,
  Loader2,
  PauseCircle,
  Pencil,
  PlayCircle,
  Plus,
  Trash2,
} from "lucide-react";

import {
  longTermTodosApi,
  type LongTermTodoSummary,
} from "@/api/longTermTodos";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "@/components/ui/toast";
import { LongTermTodoDialog } from "./LongTermTodoDialog";

const STATUS_LABEL: Record<string, string> = {
  active: "进行中",
  paused: "已暂停",
  done: "已完成",
  archived: "已归档",
};

const SCHEDULE_LABEL: Record<string, string> = {
  daily: "每天",
  weekdays: "工作日",
};

function progressPct(item: LongTermTodoSummary): number {
  if (item.total_count <= 0) return 0;
  return Math.round((item.done_count / item.total_count) * 100);
}

export function LongTermTodosPage() {
  const qc = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<LongTermTodoSummary | null>(null);

  const listQ = useQuery({
    queryKey: ["long-term-todos"],
    queryFn: () => longTermTodosApi.list(),
  });

  function invalidate() {
    qc.invalidateQueries({ queryKey: ["long-term-todos"] });
    qc.invalidateQueries({ queryKey: ["todos"] });
    qc.invalidateQueries({ queryKey: ["todo-calendar"] });
  }

  const remove = useMutation({
    mutationFn: (id: number) => longTermTodosApi.remove(id),
    onSuccess: () => {
      invalidate();
      toast.success("长期任务已删除，未完成的每日待办已一并移除");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const togglePause = useMutation({
    mutationFn: (item: LongTermTodoSummary) =>
      longTermTodosApi.update(item.id, {
        status: item.status === "active" ? "paused" : "active",
      }),
    onSuccess: () => {
      invalidate();
      toast.success("状态已更新");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const items = listQ.data?.items ?? [];

  function openCreate() {
    setEditTarget(null);
    setDialogOpen(true);
  }

  function openEdit(item: LongTermTodoSummary) {
    setEditTarget(item);
    setDialogOpen(true);
  }

  function confirmDelete(item: LongTermTodoSummary) {
    const msg =
      `确定删除长期任务「${item.title}」？\n` +
      `将同时删除 ${item.total_count - item.done_count} 条未完成的每日待办（已完成的保留记录）。`;
    if (window.confirm(msg)) remove.mutate(item.id);
  }

  return (
    <>
      <PageHeader
        title="长期任务"
        description="跨多日的重复待办（如每日刷题）· 修改或删除时自动同步日历中的每日待办"
      />
      <div className="mx-auto max-w-4xl space-y-6 p-4 md:p-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Button variant="outline" size="sm" asChild>
            <Link to="/todos">
              <ArrowLeft className="mr-2 h-4 w-4" />
              返回日历
            </Link>
          </Button>
          <Button size="sm" onClick={openCreate}>
            <Plus className="mr-2 h-4 w-4" />
            新建长期任务
          </Button>
        </div>

        {listQ.isLoading ? (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" />
            加载中…
          </div>
        ) : items.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center gap-4 py-16 text-center">
              <CalendarRange className="h-10 w-10 text-muted-foreground" />
              <div>
                <p className="font-medium">还没有长期任务</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  例如：两周内每天做一道 LeetCode，系统会自动在日历中生成每日待办。
                </p>
              </div>
              <Button onClick={openCreate}>
                <Plus className="mr-2 h-4 w-4" />
                创建第一个
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {items.map((item) => (
              <Card key={item.id}>
                <CardContent className="space-y-3 p-5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1 space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="font-semibold">{item.title}</h3>
                        <Badge variant={item.status === "active" ? "default" : "secondary"}>
                          {STATUS_LABEL[item.status] ?? item.status}
                        </Badge>
                        <Badge variant="outline">
                          {SCHEDULE_LABEL[item.schedule_mode] ?? item.schedule_mode}
                        </Badge>
                      </div>
                      {item.description ? (
                        <p className="text-sm text-muted-foreground">{item.description}</p>
                      ) : null}
                      <p className="text-sm text-muted-foreground">
                        {item.start_date} → {item.end_date} · 每日 {item.remind_time} 提醒
                      </p>
                    </div>
                    <div className="flex shrink-0 flex-wrap gap-1">
                      {item.status === "active" || item.status === "paused" ? (
                        <Button
                          variant="ghost"
                          size="icon"
                          title={item.status === "active" ? "暂停" : "恢复"}
                          onClick={() => togglePause.mutate(item)}
                          disabled={togglePause.isPending}
                        >
                          {item.status === "active" ? (
                            <PauseCircle className="h-4 w-4" />
                          ) : (
                            <PlayCircle className="h-4 w-4" />
                          )}
                        </Button>
                      ) : null}
                      <Button
                        variant="ghost"
                        size="icon"
                        title="编辑"
                        onClick={() => openEdit(item)}
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        title="删除"
                        onClick={() => confirmDelete(item)}
                        disabled={remove.isPending}
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  </div>
                  <div className="space-y-1">
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>
                        进度 {item.done_count}/{item.total_count}
                      </span>
                      <span>{progressPct(item)}%</span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-emerald-600 transition-all"
                        style={{ width: `${progressPct(item)}%` }}
                      />
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      <LongTermTodoDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        initial={editTarget}
      />
    </>
  );
}
