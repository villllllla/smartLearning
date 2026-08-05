import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CalendarRange, Loader2 } from "lucide-react";

import {
  longTermTodosApi,
  type LongTermTodoCreate,
  type LongTermTodoSummary,
  type LongTermTodoUpdate,
  type LongTermScheduleMode,
} from "@/api/longTermTodos";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/components/ui/toast";

function todayStr(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate(),
  ).padStart(2, "0")}`;
}

function addDays(base: string, days: number): string {
  const d = new Date(base + "T12:00:00");
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate(),
  ).padStart(2, "0")}`;
}

export function LongTermTodoDialog({
  open,
  onOpenChange,
  initial,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  initial?: LongTermTodoSummary | null;
}) {
  const qc = useQueryClient();
  const editing = initial != null;

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [startDate, setStartDate] = useState(todayStr());
  const [endDate, setEndDate] = useState(addDays(todayStr(), 13));
  const [remindTime, setRemindTime] = useState("21:00");
  const [scheduleMode, setScheduleMode] = useState<LongTermScheduleMode>("daily");

  useEffect(() => {
    if (!open) return;
    if (initial) {
      setTitle(initial.title);
      setDescription(initial.description ?? "");
      setStartDate(initial.start_date);
      setEndDate(initial.end_date);
      setRemindTime(initial.remind_time);
      setScheduleMode(initial.schedule_mode);
    } else {
      const t = todayStr();
      setTitle("");
      setDescription("");
      setStartDate(t);
      setEndDate(addDays(t, 13));
      setRemindTime("21:00");
      setScheduleMode("daily");
    }
  }, [open, initial]);

  function invalidate() {
    qc.invalidateQueries({ queryKey: ["long-term-todos"] });
    qc.invalidateQueries({ queryKey: ["todos"] });
    qc.invalidateQueries({ queryKey: ["todo-calendar"] });
  }

  const create = useMutation({
    mutationFn: () => {
      const body: LongTermTodoCreate = {
        title: title.trim(),
        description: description.trim() || null,
        start_date: startDate,
        end_date: endDate,
        remind_time: remindTime.trim() || "21:00",
        schedule_mode: scheduleMode,
      };
      return longTermTodosApi.create(body);
    },
    onSuccess: () => {
      invalidate();
      onOpenChange(false);
      toast.success("长期任务已创建，每日待办已生成");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const update = useMutation({
    mutationFn: () => {
      if (!initial) throw new Error("无编辑目标");
      const body: LongTermTodoUpdate = {
        title: title.trim(),
        description: description.trim() || null,
        start_date: startDate,
        end_date: endDate,
        remind_time: remindTime.trim() || "21:00",
        schedule_mode: scheduleMode,
      };
      return longTermTodosApi.update(initial.id, body);
    },
    onSuccess: () => {
      invalidate();
      onOpenChange(false);
      toast.success("长期任务已更新，未完成的每日待办已同步");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const busy = create.isPending || update.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CalendarRange className="h-5 w-5" />
            {editing ? "编辑长期任务" : "新建长期任务"}
          </DialogTitle>
          <DialogDescription>
            在起止日期内每天（或仅工作日）自动生成一条日历待办，例如每日刷一道 LeetCode。
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="space-y-2">
            <Label>事项</Label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="例如：LeetCode #42 接雨水"
            />
          </div>
          <div className="space-y-2">
            <Label>备注（可选）</Label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="题解链接、目标难度等"
              rows={2}
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>开始日期</Label>
              <Input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label>结束日期</Label>
              <Input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>每日提醒</Label>
              <Input
                type="time"
                value={remindTime}
                onChange={(e) => setRemindTime(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label>重复</Label>
              <select
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                value={scheduleMode}
                onChange={(e) =>
                  setScheduleMode(e.target.value as LongTermScheduleMode)
                }
              >
                <option value="daily">每天</option>
                <option value="weekdays">仅工作日</option>
              </select>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            disabled={!title.trim() || busy}
            onClick={() => (editing ? update.mutate() : create.mutate())}
          >
            {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            {editing ? "保存" : "创建"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
