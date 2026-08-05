import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Pencil } from "lucide-react";

import { todosApi, type TodoSummary } from "@/api/todos";
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
import { remindTimeFromUtcIso } from "@/lib/datetime";

export function EditTodoDialog({
  item,
  open,
  onOpenChange,
}: {
  item: TodoSummary | null;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const [planDate, setPlanDate] = useState("");
  const [remindTime, setRemindTime] = useState("21:00");
  const [description, setDescription] = useState("");

  useEffect(() => {
    if (!item) return;
    setTitle(item.title);
    setPlanDate(item.plan_date ?? "");
    setRemindTime(
      item.remind_at
        ? remindTimeFromUtcIso(item.remind_at, item.timezone)
        : "21:00",
    );
    setDescription(item.description ?? "");
  }, [item]);

  const save = useMutation({
    mutationFn: () =>
      todosApi.update(item!.id, {
        title: title.trim(),
        plan_date: planDate,
        remind_time: remindTime,
        description: description.trim() || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["todos"] });
      qc.invalidateQueries({ queryKey: ["todo-calendar"] });
      onOpenChange(false);
      toast.success("待办已更新");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Pencil className="h-5 w-5" />
            编辑待办
          </DialogTitle>
          <DialogDescription>
            {item?.status === "clarifying"
              ? "补充日期、提醒时间等信息后保存，待办将变为正常待办。"
              : item?.status === "done"
                ? "可修改已完成待办的事项、日期与提醒时间，不会自动改变完成状态。"
                : "可修改今天及以后待办的事项、日期与提醒时间。"}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>事项</Label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>日期</Label>
              <Input type="date" value={planDate} onChange={(e) => setPlanDate(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>提醒时间</Label>
              <Input type="time" value={remindTime} onChange={(e) => setRemindTime(e.target.value)} />
            </div>
          </div>
          <div className="space-y-2">
            <Label>备注</Label>
            <Textarea
              rows={4}
              maxLength={2000}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            onClick={() => title.trim() && planDate && save.mutate()}
            disabled={!title.trim() || !planDate || save.isPending}
          >
            {save.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
