import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CalendarRange,
  FileUp,
  Loader2,
  Sparkles,
  Trash2,
  Wand2,
} from "lucide-react";

import {
  plansApi,
  type PlanPreviewResponse,
  type PlanTaskDraft,
} from "@/api/plans";
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

export function PlanImportDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [step, setStep] = useState<"form" | "preview">("form");
  const [title, setTitle] = useState("");
  const [goal, setGoal] = useState("");
  const [fileName, setFileName] = useState("");
  const [start, setStart] = useState(todayStr());
  const [end, setEnd] = useState("");
  const [preview, setPreview] = useState<PlanPreviewResponse | null>(null);
  const [tasks, setTasks] = useState<PlanTaskDraft[]>([]);

  const GOAL_MAX = 100_000;

  function reset() {
    setStep("form");
    setTitle("");
    setGoal("");
    setFileName("");
    setStart(todayStr());
    setEnd("");
    setPreview(null);
    setTasks([]);
  }

  async function onPickFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-picking same file
    if (!file) return;
    try {
      const text = await file.text();
      if (text.length > GOAL_MAX) {
        toast.error(`文件过大（${text.length} 字符），上限 ${GOAL_MAX} 字符`);
        return;
      }
      setGoal(text);
      setFileName(file.name);
      if (!title.trim()) setTitle(file.name.replace(/\.[^.]+$/, ""));
      toast.success(`已导入文件「${file.name}」（${text.length} 字符）`);
    } catch {
      toast.error("读取文件失败，请使用纯文本 / Markdown 文件");
    }
  }

  function close(v: boolean) {
    if (!v) reset();
    onOpenChange(v);
  }

  const previewM = useMutation({
    mutationFn: () =>
      plansApi.preview({ title, goal, start_date: start, end_date: end }),
    onSuccess: (res) => {
      setPreview(res);
      setTasks(res.tasks);
      setStep("preview");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const createM = useMutation({
    mutationFn: () =>
      plansApi.create({
        title,
        goal,
        start_date: start,
        end_date: end,
        tasks,
        prompt_id: preview?.prompt_id ?? null,
        model_id: preview?.model_id ?? null,
      }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["todos"] });
      qc.invalidateQueries({ queryKey: ["todo-calendar"] });
      qc.invalidateQueries({ queryKey: ["plans"] });
      toast.success(`已导入「${res.title}」，共 ${res.total_count} 个任务`);
      close(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  function removeTask(i: number) {
    setTasks((prev) => prev.filter((_, idx) => idx !== i));
  }

  const canPreview = title.trim() && start && end && end >= start;

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5" />
            导入计划（模型自动分解）
          </DialogTitle>
          <DialogDescription>
            {step === "form"
              ? "填写目标与时间区间，模型会把它拆成按天分布的小任务。"
              : "确认分解结果，可删除不需要的任务，确认后写入未来待办。"}
          </DialogDescription>
        </DialogHeader>

        {step === "form" ? (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>计划标题</Label>
              <Input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="例如：两周搞定 LeetCode 动态规划"
              />
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label>目标 / 说明</Label>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">
                    {goal.length}/{GOAL_MAX}
                    {fileName ? ` · ${fileName}` : ""}
                  </span>
                  <input
                    ref={fileRef}
                    type="file"
                    accept=".txt,.md,.markdown,.text,.csv,.json,.log"
                    className="hidden"
                    onChange={onPickFile}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => fileRef.current?.click()}
                  >
                    <FileUp className="mr-2 h-3.5 w-3.5" />
                    从文件导入
                  </Button>
                </div>
              </div>
              <Textarea
                rows={5}
                value={goal}
                onChange={(e) => {
                  setGoal(e.target.value);
                  if (fileName) setFileName("");
                }}
                placeholder="想达成什么？可直接粘贴长文档，或点「从文件导入」上传纯文本 / Markdown 计划"
              />
              <p className="text-xs text-muted-foreground">
                支持 .txt / .md 等纯文本文件；上限 {GOAL_MAX.toLocaleString()} 字符（受模型上下文限制）。
              </p>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>开始日期</Label>
                <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label>结束日期</Label>
                <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
              </div>
            </div>
          </div>
        ) : (
          <div className="max-h-[50vh] space-y-2 overflow-y-auto pr-1">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <CalendarRange className="h-4 w-4" />
              共分解出 {tasks.length} 个任务（{start} ~ {end}）
            </div>
            {tasks.map((t, i) => (
              <div
                key={`${t.date}-${i}`}
                className="flex items-start justify-between gap-3 rounded-md border p-3"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-primary/10 px-1.5 py-0.5 text-xs font-medium text-primary">
                      {t.date}
                    </span>
                    <span className="font-medium">{t.title}</span>
                  </div>
                  {t.description ? (
                    <p className="mt-1 text-sm text-muted-foreground">{t.description}</p>
                  ) : null}
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => removeTask(i)}
                  className="shrink-0"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}
            {tasks.length === 0 ? (
              <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
                没有任务了，请返回调整目标重新分解
              </div>
            ) : null}
          </div>
        )}

        <DialogFooter>
          {step === "form" ? (
            <>
              <Button variant="ghost" onClick={() => close(false)}>
                取消
              </Button>
              <Button
                onClick={() => previewM.mutate()}
                disabled={!canPreview || previewM.isPending}
              >
                {previewM.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Wand2 className="mr-2 h-4 w-4" />
                )}
                模型分解
              </Button>
            </>
          ) : (
            <>
              <Button variant="ghost" onClick={() => setStep("form")}>
                返回修改
              </Button>
              <Button
                onClick={() => createM.mutate()}
                disabled={tasks.length === 0 || createM.isPending}
              >
                {createM.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : null}
                确认导入 {tasks.length} 项
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
