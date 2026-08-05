import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";

import { type Scene, promptsApi } from "@/api/prompts";
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

interface Props {
  open: boolean;
  scene: Scene;
  initialName?: string;
  initialContent?: string;
  onOpenChange: (open: boolean) => void;
  onCreated?: () => void;
}

const PLACEHOLDER_HINT: Record<Scene, string> = {
  chat_general: "对话 system prompt;一般不需要变量。",
  wiki_to_questions: "需包含 {N}、{TITLE}、{MARKDOWN}",
  answer_scoring: "需包含 {QUESTION}、{ANSWER_STANDARD}、{USER_ANSWER}",
  wiki_summary: "需包含 {TITLE}、{MARKDOWN}",
  learning_note_structuring: "需包含 {RAW_INPUT}",
  todo_intent_parsing:
    "需包含 {TIMEZONE}、{NOW_LOCAL}、{CONTEXT_JSON}、{USER_MESSAGE}",
  ai_news_curation: "需包含 {TOP_N}、{CANDIDATES_JSON}",
  plan_decomposition:
    "需包含 {TITLE}、{GOAL}、{START_DATE}、{END_DATE}、{TODAY}、{TIMEZONE}",
  todo_motivation: "需包含 {TASK_TITLE}、{DEFER_DAYS}",
  interview_answer_generation: "需包含 {CONTEXT}、{GROUP_LABEL}、{QUESTIONS_JSON}",
};

export function CreateVersionDialog({
  open,
  scene,
  initialName,
  initialContent,
  onOpenChange,
  onCreated,
}: Props) {
  const [name, setName] = useState(initialName ?? "");
  const [content, setContent] = useState(initialContent ?? "");
  const [notes, setNotes] = useState("");
  const [setCurrent, setSetCurrent] = useState(true);

  const create = useMutation({
    mutationFn: () =>
      promptsApi.createVersion({
        scene,
        name: name.trim(),
        content,
        notes: notes.trim() || null,
        set_current: setCurrent,
      }),
    onSuccess: (v) => {
      toast.success(`v${v.version_no} 已创建${v.is_current ? " · 当前生效" : ""}`);
      onCreated?.();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const submit = () => {
    if (!name.trim()) {
      toast.error("请填写版本名称");
      return;
    }
    if (content.trim().length < 10) {
      toast.error("Prompt 内容至少 10 个字符");
      return;
    }
    create.mutate();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>新建 Prompt 版本</DialogTitle>
          <DialogDescription>
            场景:{scene} · {PLACEHOLDER_HINT[scene]}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="pv-name">版本名称</Label>
            <Input
              id="pv-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="如:生成面试题 v2"
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="pv-content">
              Prompt 内容
              <span className="ml-2 text-[11px] font-normal text-muted-foreground">
                (使用 {"{NAME}"} 风格的占位符)
              </span>
            </Label>
            <Textarea
              id="pv-content"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={16}
              className="font-mono text-xs leading-relaxed"
              placeholder="[系统角色]\n你是..."
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="pv-notes">备注(可选)</Label>
            <Input
              id="pv-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="改动了什么、为什么"
            />
          </div>
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="h-4 w-4"
              checked={setCurrent}
              onChange={(e) => setSetCurrent(e.target.checked)}
            />
            创建后立即设为当前生效版本
          </label>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={create.isPending}>
            取消
          </Button>
          <Button onClick={submit} disabled={create.isPending}>
            <Sparkles className="h-4 w-4" />
            {create.isPending ? "创建中..." : "创建版本"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
