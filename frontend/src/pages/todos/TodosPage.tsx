import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarPlus,
  CalendarRange,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ListTodo,
  Loader2,
  PauseCircle,
  Pencil,
  PlayCircle,
  Plus,
  Sparkles,
  Trash2,
  Trophy,
  Undo2,
  XCircle,
} from "lucide-react";

import { todosApi, type TodoListResponse, type TodoSummary } from "@/api/todos";
import { longTermTodosApi } from "@/api/longTermTodos";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { canEditTodo, formatTodoRemindAt } from "@/lib/datetime";
import { cn } from "@/lib/utils";
import { EditTodoDialog } from "./EditTodoDialog";
import { TodoDescriptionPreview } from "./TodoDescriptionPreview";
import { TodoProgressSlider } from "./TodoProgressSlider";
import { PlanImportDialog } from "./PlanImportDialog";
import { QuickAddDialog } from "./QuickAddDialog";
import { SnoozeDialog } from "./SnoozeDialog";

const STATUS_LABEL: Record<string, string> = {
  clarifying: "待补充",
  scheduled: "待办",
  reminded: "已提醒",
  snoozed: "已挂起",
  done: "已完成",
  cancelled: "已取消",
};

const WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"];

function pad(n: number): string {
  return String(n).padStart(2, "0");
}
function fmt(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
function startOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}
function buildGrid(month: Date): Date[] {
  const first = startOfMonth(month);
  const mondayOffset = (first.getDay() + 6) % 7;
  const s = new Date(first);
  s.setDate(first.getDate() - mondayOffset);
  return Array.from({ length: 42 }, (_, i) => {
    const d = new Date(s);
    d.setDate(s.getDate() + i);
    return d;
  });
}
function heatClass(total: number, done: number, isPast: boolean): string {
  if (isPast) {
    if (total === 0) return "bg-muted/25 hover:bg-muted/45 text-muted-foreground/60";
    if (done >= total) return "bg-slate-600/45 text-slate-200 hover:bg-slate-600/60";
    if (total >= 4) return "bg-slate-500/80 text-white hover:bg-slate-500";
    if (total >= 3) return "bg-slate-600/70 text-white hover:bg-slate-600/85";
    if (total >= 2) return "bg-slate-700/65 text-slate-100 hover:bg-slate-700/80";
    return "bg-slate-800/55 text-slate-200 hover:bg-slate-800/70";
  }
  if (total === 0) return "bg-muted/20 hover:bg-muted/40 text-muted-foreground";
  if (done >= total) return "bg-emerald-800/50 text-emerald-100 hover:bg-emerald-800/70";
  if (total >= 4) return "bg-emerald-500 text-white hover:bg-emerald-400";
  if (total >= 3) return "bg-emerald-600 text-white hover:bg-emerald-500";
  if (total >= 2) return "bg-emerald-700/80 text-white hover:bg-emerald-600";
  return "bg-emerald-900/70 text-emerald-100 hover:bg-emerald-800/80";
}

function progressStatus(
  item: TodoSummary,
  progress: number,
): Pick<TodoSummary, "status" | "progress" | "completed_at"> {
  if (progress >= 100) {
    return { progress, status: "done", completed_at: new Date().toISOString() };
  }
  if (item.status === "done") {
    return {
      progress,
      status: item.reminded_at ? "reminded" : "scheduled",
      completed_at: null,
    };
  }
  return { progress, status: item.status, completed_at: item.completed_at };
}

function addDays(base: string, days: number): string {
  const d = new Date(base + "T12:00:00");
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function TodosPage() {
  const qc = useQueryClient();
  const todayStr = fmt(new Date());

  const [title, setTitle] = useState("");
  const [planDate, setPlanDate] = useState(todayStr);
  const [remindTime, setRemindTime] = useState("21:00");
  const [createMode, setCreateMode] = useState<"single" | "long_term">("single");
  const [ltStart, setLtStart] = useState(todayStr);
  const [ltEnd, setLtEnd] = useState(() => addDays(todayStr, 13));
  const [ltSchedule, setLtSchedule] = useState<"daily" | "weekdays">("daily");
  const [viewMonth, setViewMonth] = useState(() => startOfMonth(new Date()));
  const [selectedDay, setSelectedDay] = useState(todayStr);
  const [planOpen, setPlanOpen] = useState(false);
  const [quickOpen, setQuickOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<TodoSummary | null>(null);
  const [snoozeTarget, setSnoozeTarget] = useState<TodoSummary | null>(null);

  useEffect(() => {
    setPlanDate(selectedDay);
  }, [selectedDay]);

  const grid = useMemo(() => buildGrid(viewMonth), [viewMonth]);
  const rangeStart = fmt(grid[0]);
  const rangeEnd = fmt(grid[41]);

  const calQ = useQuery({
    queryKey: ["todo-calendar", rangeStart, rangeEnd],
    queryFn: () => todosApi.calendar(rangeStart, rangeEnd),
  });
  const countsByDay = useMemo(() => {
    const m = new Map<string, { total: number; done: number }>();
    for (const d of calQ.data?.days ?? []) m.set(d.date, { total: d.total, done: d.done });
    return m;
  }, [calQ.data]);

  const dayQ = useQuery({
    queryKey: ["todos", "day", selectedDay],
    queryFn: () => todosApi.list({ day: selectedDay }),
  });

  function invalidateAll() {
    qc.invalidateQueries({ queryKey: ["todos"] });
    qc.invalidateQueries({ queryKey: ["todo-calendar"] });
  }

  const create = useMutation({
    mutationFn: () =>
      todosApi.create({
        title: title.trim(),
        plan_date: planDate,
        remind_time: remindTime.trim() || "21:00",
      }),
    onSuccess: () => {
      setTitle("");
      setRemindTime("21:00");
      invalidateAll();
      toast.success("待办已创建");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const createLongTerm = useMutation({
    mutationFn: () =>
      longTermTodosApi.create({
        title: title.trim(),
        start_date: ltStart,
        end_date: ltEnd,
        remind_time: remindTime.trim() || "21:00",
        schedule_mode: ltSchedule,
      }),
    onSuccess: () => {
      setTitle("");
      setRemindTime("21:00");
      invalidateAll();
      toast.success("长期任务已创建，每日待办已加入日历");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const done = useMutation({
    mutationFn: (id: number) => todosApi.done(id),
    onSuccess: () => {
      invalidateAll();
      toast.success("已标记完成");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const setProgress = useMutation({
    mutationFn: (v: { id: number; progress: number }) =>
      todosApi.setProgress(v.id, v.progress),
    onMutate: async (v) => {
      await qc.cancelQueries({ queryKey: ["todos", "day", selectedDay] });
      const prev = qc.getQueryData<TodoListResponse>(["todos", "day", selectedDay]);
      qc.setQueryData<TodoListResponse>(["todos", "day", selectedDay], (old) => {
        if (!old) return old;
        return {
          ...old,
          items: old.items.map((t) =>
            t.id === v.id ? { ...t, ...progressStatus(t, v.progress) } : t,
          ),
        };
      });
      return { prev };
    },
    onError: (e: Error, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(["todos", "day", selectedDay], ctx.prev);
      toast.error(e.message);
    },
    onSuccess: (data) => {
      qc.setQueryData<TodoListResponse>(["todos", "day", selectedDay], (old) => {
        if (!old) return old;
        return {
          ...old,
          items: old.items.map((t) => (t.id === data.id ? data : t)),
        };
      });
      qc.invalidateQueries({ queryKey: ["todo-calendar"] });
      if (data.status === "done") toast.success("进度 100%，已标记完成");
    },
  });
  const cancel = useMutation({
    mutationFn: (id: number) => todosApi.cancel(id),
    onSuccess: () => {
      invalidateAll();
      toast.success("已取消");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const restore = useMutation({
    mutationFn: (id: number) => todosApi.restore(id),
    onSuccess: () => {
      invalidateAll();
      toast.success("已撤销取消");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: (id: number) => todosApi.remove(id),
    onSuccess: () => {
      invalidateAll();
      toast.success("待办已删除");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const unsnooze = useMutation({
    mutationFn: (id: number) => todosApi.unsnooze(id),
    onSuccess: () => {
      invalidateAll();
      toast.success("已恢复");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const snooze = useMutation({
    mutationFn: (v: { id: number; until: string; note: string }) =>
      todosApi.snooze(v.id, v.until, v.note),
    onSuccess: () => {
      invalidateAll();
      setSnoozeTarget(null);
      toast.success("已挂起");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const items = dayQ.data?.items ?? [];
  const monthLabel = `${viewMonth.getFullYear()}年${viewMonth.getMonth() + 1}月`;
  const busy =
    done.isPending ||
    cancel.isPending ||
    restore.isPending ||
    remove.isPending ||
    unsnooze.isPending;

  function confirmDelete(item: TodoSummary) {
    if (window.confirm(`确定删除待办「${item.title}」？`)) {
      remove.mutate(item.id);
    }
  }

  return (
    <>
      <PageHeader
        title="待办 · 计划日历"
        description="按日历安排每日任务 · 导入大计划自动分解 · 过期自动顺延 · 到点飞书提醒"
      />
      <div className="mx-auto max-w-5xl space-y-6 p-4 md:p-8">
        <Card>
          <CardContent className="space-y-4 p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-sm font-medium">
                <ListTodo className="h-4 w-4" />
                新建待办
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" size="sm" asChild>
                  <Link to="/todos/long-term">
                    <CalendarRange className="mr-2 h-4 w-4" />
                    长期任务
                  </Link>
                </Button>
                <Button variant="outline" size="sm" onClick={() => setQuickOpen(true)}>
                  <Sparkles className="mr-2 h-4 w-4" />
                  快速新增
                </Button>
                <Button variant="outline" size="sm" onClick={() => setPlanOpen(true)}>
                  <CalendarPlus className="mr-2 h-4 w-4" />
                  导入计划
                </Button>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                size="sm"
                variant={createMode === "single" ? "default" : "outline"}
                onClick={() => setCreateMode("single")}
              >
                单日待办
              </Button>
              <Button
                type="button"
                size="sm"
                variant={createMode === "long_term" ? "default" : "outline"}
                onClick={() => setCreateMode("long_term")}
              >
                长期任务
              </Button>
            </div>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div className="space-y-2 sm:col-span-2 lg:col-span-2">
                <Label>事项</Label>
                <Input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder={
                    createMode === "long_term"
                      ? "例如：LeetCode #42 接雨水"
                      : "例如：交周报"
                  }
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && title.trim()) {
                      createMode === "long_term"
                        ? createLongTerm.mutate()
                        : create.mutate();
                    }
                  }}
                />
              </div>
              {createMode === "single" ? (
                <div className="space-y-2">
                  <Label>日期</Label>
                  <Input
                    type="date"
                    value={planDate}
                    onChange={(e) => setPlanDate(e.target.value)}
                  />
                </div>
              ) : (
                <>
                  <div className="space-y-2">
                    <Label>开始</Label>
                    <Input
                      type="date"
                      value={ltStart}
                      onChange={(e) => setLtStart(e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>结束</Label>
                    <Input
                      type="date"
                      value={ltEnd}
                      onChange={(e) => setLtEnd(e.target.value)}
                    />
                  </div>
                </>
              )}
              <div className="space-y-2">
                <Label>提醒时间</Label>
                <Input
                  type="time"
                  value={remindTime}
                  onChange={(e) => setRemindTime(e.target.value)}
                />
              </div>
              {createMode === "long_term" ? (
                <div className="space-y-2 sm:col-span-2">
                  <Label>重复</Label>
                  <select
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    value={ltSchedule}
                    onChange={(e) =>
                      setLtSchedule(e.target.value as "daily" | "weekdays")
                    }
                  >
                    <option value="daily">每天</option>
                    <option value="weekdays">仅工作日</option>
                  </select>
                </div>
              ) : null}
            </div>
            <div className="flex justify-end">
              <Button
                onClick={() =>
                  createMode === "long_term"
                    ? title.trim() && createLongTerm.mutate()
                    : title.trim() && create.mutate()
                }
                disabled={
                  !title.trim() ||
                  create.isPending ||
                  createLongTerm.isPending
                }
              >
                {(create.isPending || createLongTerm.isPending) ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Plus className="mr-2 h-4 w-4" />
                )}
                {createMode === "long_term" ? "创建长期任务" : "添加"}
              </Button>
            </div>
          </CardContent>
        </Card>

        <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
          <Card>
            <CardContent className="space-y-3 p-5">
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold">{monthLabel}</div>
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      setViewMonth(new Date(viewMonth.getFullYear(), viewMonth.getMonth() - 1, 1))
                    }
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setViewMonth(startOfMonth(new Date()));
                      setSelectedDay(todayStr);
                    }}
                  >
                    今天
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      setViewMonth(new Date(viewMonth.getFullYear(), viewMonth.getMonth() + 1, 1))
                    }
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>

              <div className="grid grid-cols-7 gap-1 text-center text-xs text-muted-foreground">
                {WEEKDAYS.map((w) => (
                  <div key={w} className="py-1">
                    {w}
                  </div>
                ))}
              </div>
              <div className="grid grid-cols-7 gap-1">
                {grid.map((d) => {
                  const ds = fmt(d);
                  const inMonth = d.getMonth() === viewMonth.getMonth();
                  const c = countsByDay.get(ds);
                  const total = c?.total ?? 0;
                  const doneCount = c?.done ?? 0;
                  const isToday = ds === todayStr;
                  const isPast = ds < todayStr;
                  const isSelected = ds === selectedDay;
                  const allDone = total > 0 && doneCount >= total;
                  return (
                    <button
                      key={ds}
                      type="button"
                      onClick={() => setSelectedDay(ds)}
                      title={
                        total > 0
                          ? allDone
                            ? `${total} 项 · 全部完成`
                            : `${total} 项 · 完成 ${doneCount}`
                          : "无计划"
                      }
                      className={cn(
                        "relative flex aspect-square flex-col items-center justify-center rounded-md text-sm transition-colors",
                        heatClass(total, doneCount, isPast),
                        !inMonth && "opacity-40",
                        isSelected && "ring-2 ring-primary",
                        isToday && !isSelected && "ring-1 ring-primary/50",
                      )}
                    >
                      <span>{d.getDate()}</span>
                      {allDone ? (
                        <span
                          className={cn(
                            "flex h-4 w-4 items-center justify-center rounded-full",
                            isPast
                              ? "bg-amber-500/30 text-amber-200 ring-1 ring-amber-400/35"
                              : "bg-gradient-to-br from-amber-300 to-amber-500 text-amber-950 shadow-sm ring-1 ring-amber-200/60",
                          )}
                          aria-hidden
                        >
                          <Trophy className="h-2.5 w-2.5" strokeWidth={2.25} />
                        </span>
                      ) : total > 0 ? (
                        <span className="text-[10px] leading-none opacity-90">{total}</span>
                      ) : null}
                    </button>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-3 p-5">
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold">
                  {selectedDay === todayStr ? "今日计划" : selectedDay}
                </div>
                <Badge variant="outline">{items.length} 项</Badge>
              </div>

              {dayQ.isLoading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" /> 加载中…
                </div>
              ) : items.length === 0 ? (
                <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
                  {selectedDay === todayStr
                    ? "今天还没有安排计划 —— 快速新建一个，或「导入计划」让模型帮你排。"
                    : "这一天暂无计划"}
                </div>
              ) : (
                <div className="space-y-3">
                  {items.map((t) => (
                    <TodoRow
                      key={t.id}
                      item={t}
                      busy={busy}
                      onDone={() => done.mutate(t.id)}
                      onProgress={(p) => setProgress.mutate({ id: t.id, progress: p })}
                      onCancel={() => cancel.mutate(t.id)}
                      onRestore={() => restore.mutate(t.id)}
                      onDelete={() => confirmDelete(t)}
                      onSnooze={() => setSnoozeTarget(t)}
                      onUnsnooze={() => unsnooze.mutate(t.id)}
                      onEdit={() => setEditTarget(t)}
                    />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      <PlanImportDialog open={planOpen} onOpenChange={setPlanOpen} />
      <QuickAddDialog open={quickOpen} onOpenChange={setQuickOpen} />
      <EditTodoDialog
        item={editTarget}
        open={editTarget !== null}
        onOpenChange={(v) => !v && setEditTarget(null)}
      />
      <SnoozeDialog
        open={snoozeTarget !== null}
        onOpenChange={(v) => !v && setSnoozeTarget(null)}
        taskTitle={snoozeTarget?.title ?? ""}
        busy={snooze.isPending}
        onConfirm={(until, note) =>
          snoozeTarget && snooze.mutate({ id: snoozeTarget.id, until, note })
        }
      />
    </>
  );
}

function TodoRow({
  item,
  onDone,
  onProgress,
  onCancel,
  onRestore,
  onDelete,
  onSnooze,
  onUnsnooze,
  onEdit,
  busy,
}: {
  item: TodoSummary;
  onDone: () => void;
  onProgress: (progress: number) => void;
  onCancel: () => void;
  onRestore: () => void;
  onDelete: () => void;
  onSnooze: () => void;
  onUnsnooze: () => void;
  onEdit: () => void;
  busy: boolean;
}) {
  const when = item.remind_at
    ? formatTodoRemindAt(item.remind_at, item.timezone)
    : null;
  const editable = canEditTodo(item);
  const clarifying = item.status === "clarifying";
  const active = item.status === "scheduled" || item.status === "reminded";
  const cancelled = item.status === "cancelled";
  const doneStatus = item.status === "done";
  const showProgress =
    item.status === "scheduled" ||
    item.status === "reminded" ||
    (doneStatus && (item.progress ?? 0) > 0);
  return (
    <div className="overflow-hidden rounded-md border px-5 py-4 space-y-3">
      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{item.title}</span>
          <Badge variant="outline">{STATUS_LABEL[item.status] ?? item.status}</Badge>
          {item.plan_id ? <Badge variant="secondary">计划</Badge> : null}
          {item.long_term_id ? <Badge variant="secondary">长期</Badge> : null}
        </div>
        {item.description ? (
          <TodoDescriptionPreview
            text={item.description}
            editable={editable}
            busy={busy}
            onEdit={onEdit}
          />
        ) : null}
        {item.clarification_question ? (
          <p className="text-sm text-amber-600">待补充: {item.clarification_question}</p>
        ) : null}
        {item.defer_count > 0 && item.original_plan_date ? (
          <p className="text-xs text-orange-500">
            ⏳ 原计划 {item.original_plan_date} · 已延期 {item.defer_count} 天
          </p>
        ) : null}
        {item.status === "snoozed" ? (
          <p className="text-xs text-sky-500">
            已挂起至 {item.snooze_until}
            {item.snooze_note ? ` · ${item.snooze_note}` : ""}
          </p>
        ) : null}
        {when ? <p className="text-xs text-muted-foreground">提醒: {when}</p> : null}
      </div>
      <div className="flex flex-wrap gap-2">
          {editable ? (
            <Button
              size="sm"
              variant={clarifying ? "default" : "outline"}
              onClick={onEdit}
              disabled={busy}
            >
              <Pencil className="mr-1 h-3.5 w-3.5" /> {clarifying ? "补充信息" : "编辑"}
            </Button>
          ) : null}
          {clarifying ? (
            <>
              <Button size="sm" variant="ghost" onClick={onCancel} disabled={busy}>
                <XCircle className="mr-1 h-3.5 w-3.5" /> 取消
              </Button>
              <Button size="sm" variant="ghost" onClick={onDelete} disabled={busy}>
                <Trash2 className="mr-1 h-3.5 w-3.5" /> 删除
              </Button>
            </>
          ) : null}
          {active ? (
            <>
              <Button size="sm" variant="outline" onClick={onDone} disabled={busy}>
                <CheckCircle2 className="mr-1 h-3.5 w-3.5" /> 完成
              </Button>
              <Button size="sm" variant="ghost" onClick={onSnooze} disabled={busy}>
                <PauseCircle className="mr-1 h-3.5 w-3.5" /> 挂起
              </Button>
              <Button size="sm" variant="ghost" onClick={onCancel} disabled={busy}>
                <XCircle className="mr-1 h-3.5 w-3.5" /> 取消
              </Button>
              <Button size="sm" variant="ghost" onClick={onDelete} disabled={busy}>
                <Trash2 className="mr-1 h-3.5 w-3.5" /> 删除
              </Button>
            </>
          ) : item.status === "snoozed" ? (
            <>
              <Button size="sm" variant="outline" onClick={onUnsnooze} disabled={busy}>
                <PlayCircle className="mr-1 h-3.5 w-3.5" /> 恢复
              </Button>
              <Button size="sm" variant="ghost" onClick={onDelete} disabled={busy}>
                <Trash2 className="mr-1 h-3.5 w-3.5" /> 删除
              </Button>
            </>
          ) : cancelled ? (
            <>
              <Button size="sm" variant="outline" onClick={onRestore} disabled={busy}>
                <Undo2 className="mr-1 h-3.5 w-3.5" /> 撤销
              </Button>
              <Button size="sm" variant="ghost" onClick={onDelete} disabled={busy}>
                <Trash2 className="mr-1 h-3.5 w-3.5" /> 删除
              </Button>
            </>
          ) : doneStatus ? (
            <>
              <Button size="sm" variant="ghost" onClick={onDelete} disabled={busy}>
                <Trash2 className="mr-1 h-3.5 w-3.5" /> 删除
              </Button>
            </>
          ) : null}
      </div>
      {showProgress ? (
        <TodoProgressSlider
          className="ml-1 w-2/3 max-w-full"
          value={item.progress ?? 0}
          disabled={busy}
          onChange={onProgress}
        />
      ) : null}
    </div>
  );
}
