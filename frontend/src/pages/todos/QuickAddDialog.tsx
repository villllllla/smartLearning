import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Send, Sparkles } from "lucide-react";

import { todosApi } from "@/api/todos";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/components/ui/toast";

export function QuickAddDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState("");

  const parse = useMutation({
    mutationFn: (text: string) => todosApi.parse(text),
    onSuccess: (item) => {
      setDraft("");
      onOpenChange(false);
      qc.invalidateQueries({ queryKey: ["todos"] });
      qc.invalidateQueries({ queryKey: ["todo-calendar"] });
      if (item.status === "clarifying") {
        toast.success("请在本页点击「补充信息」完善待办");
      } else {
        toast.success("待办已创建");
      }
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) setDraft("");
        onOpenChange(v);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5" />
            快速新增
          </DialogTitle>
          <DialogDescription>
            用一句话描述待办，系统会自动识别事项与时间，例如「明天下午3点提醒我交周报」。
          </DialogDescription>
        </DialogHeader>
        <Textarea
          rows={3}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="例如：明天下午3点提醒我交周报"
        />
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            onClick={() => draft.trim() && parse.mutate(draft.trim())}
            disabled={!draft.trim() || parse.isPending}
          >
            {parse.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Send className="mr-2 h-4 w-4" />
            )}
            解析并创建
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
