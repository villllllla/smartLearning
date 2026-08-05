import { useState } from "react";
import { PauseCircle } from "lucide-react";

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

export function SnoozeDialog({
  open,
  onOpenChange,
  taskTitle,
  onConfirm,
  busy,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  taskTitle: string;
  onConfirm: (until: string, note: string) => void;
  busy?: boolean;
}) {
  const [until, setUntil] = useState("");
  const [note, setNote] = useState("");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <PauseCircle className="h-5 w-5" />
            挂起任务
          </DialogTitle>
          <DialogDescription>
            「{taskTitle}」将暂停顺延，到预计日期自动恢复到当天待办。
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>预计进行日期</Label>
            <Input type="date" value={until} onChange={(e) => setUntil(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>备注（可选）</Label>
            <Textarea
              rows={3}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="例如：等考试结束后再继续"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            onClick={() => until && onConfirm(until, note)}
            disabled={!until || busy}
          >
            确认挂起
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
