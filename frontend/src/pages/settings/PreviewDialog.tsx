import { useEffect, useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { type Scene, promptsApi } from "@/api/prompts";
import { Badge } from "@/components/ui/badge";
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

interface Props {
  open: boolean;
  scene: Scene;
  content: string;
  onOpenChange: (open: boolean) => void;
}

const SAMPLE_VARS: Record<Scene, Record<string, string>> = {
  chat_general: {},
  wiki_to_questions: {
    N: "12",
    TITLE: "JVM 内存模型",
    MARKDOWN:
      "# JVM 内存模型\n\n描述堆 / 栈 / 元空间的划分,以及 GC roots、对象可达性分析。",
  },
  answer_scoring: {
    QUESTION: "请简述 JVM 中堆与栈的区别",
    ANSWER_STANDARD:
      "结论:作用域不同;栈线程私有,堆线程共享。要点:对象生命周期、GC 关注堆。",
    USER_ANSWER: "栈是放方法调用的,堆是放对象的。",
  },
  wiki_summary: {
    TITLE: "JVM 内存模型",
    MARKDOWN:
      "# JVM 内存模型\n\n描述堆 / 栈 / 元空间的划分,以及 GC roots、对象可达性分析。",
  },
  learning_note_structuring: {
    RAW_INPUT: "今天学习了 Redis 的 RDB 与 AOF 持久化机制…",
  },
  todo_intent_parsing: {
    TIMEZONE: "Asia/Shanghai",
    NOW_LOCAL: "2026-06-23 14:30 Monday",
    CONTEXT_JSON: "[]",
    USER_MESSAGE: "明天下午3点提醒我交周报",
  },
  ai_news_curation: {
    TOP_N: "5",
    CANDIDATES_JSON:
      '[{"id":1,"title":"OpenAI releases new model","source":"HackerNews","url":"https://example.com","score":320}]',
  },
  plan_decomposition: {
    TITLE: "两周搞定 LeetCode 动态规划",
    GOAL: "系统刷完 DP 常见题型并能独立解中等难度题",
    START_DATE: "2026-07-14",
    END_DATE: "2026-07-27",
    TODAY: "2026-07-12",
    TIMEZONE: "Asia/Shanghai",
  },
  todo_motivation: {
    TASK_TITLE: "做一遍 leetcode 题",
    DEFER_DAYS: "4",
  },
  interview_answer_generation: {
    CONTEXT: "某电商公司 Java 后端一面,项目为高并发秒杀系统。",
    GROUP_LABEL: "秒杀项目 / 一面",
    QUESTIONS_JSON:
      '[{"index":0,"question":"秒杀场景下如何防止超卖?"},{"index":1,"question":"承接上题,库存扣减放 Redis 还是 DB?"}]',
  },
};

export function PreviewDialog({ open, scene, content, onOpenChange }: Props) {
  const [vars, setVars] = useState<Record<string, string>>(SAMPLE_VARS[scene] ?? {});
  useEffect(() => {
    setVars(SAMPLE_VARS[scene] ?? {});
  }, [scene]);

  const placeholdersInTpl = useMemo(() => {
    const re = /\{([A-Z_][A-Z0-9_]*)\}/g;
    return Array.from(new Set(Array.from(content.matchAll(re)).map((m) => m[1])));
  }, [content]);

  // Ensure each detected placeholder has an input row
  useEffect(() => {
    setVars((prev) => {
      const next = { ...prev };
      for (const p of placeholdersInTpl) {
        if (!(p in next)) next[p] = "";
      }
      return next;
    });
  }, [placeholdersInTpl]);

  const preview = useMutation({
    mutationFn: () => promptsApi.preview({ content, variables: vars }),
  });

  const result = preview.data;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>预览渲染</DialogTitle>
          <DialogDescription>
            填入示例变量值,看看 prompt 实际发送给模型时长什么样。
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-3">
          <div className="grid gap-2">
            <Label className="text-xs">变量值(模板中检测到 {placeholdersInTpl.length} 个占位符)</Label>
            {placeholdersInTpl.length === 0 && (
              <div className="text-xs text-muted-foreground">
                此模板没有占位符,无需变量。
              </div>
            )}
            {placeholdersInTpl.map((p) => (
              <div key={p} className="grid grid-cols-[120px_1fr] items-start gap-2">
                <code className="rounded bg-muted px-1.5 py-1 text-center font-mono text-[11px]">
                  {"{" + p + "}"}
                </code>
                <Input
                  value={vars[p] ?? ""}
                  onChange={(e) => setVars((prev) => ({ ...prev, [p]: e.target.value }))}
                  placeholder={`填入 ${p} 的示例值`}
                />
              </div>
            ))}
          </div>

          <div className="flex justify-end">
            <Button size="sm" onClick={() => preview.mutate()} disabled={preview.isPending}>
              {preview.isPending ? "渲染中..." : "渲染预览"}
            </Button>
          </div>

          {result && (
            <div className="grid gap-2">
              {(result.missing_placeholders.length > 0 ||
                result.unused_variables.length > 0) && (
                <div className="flex flex-wrap gap-2 text-xs">
                  {result.missing_placeholders.map((p) => (
                    <Badge key={`m-${p}`} variant="warning">
                      模板未填:{p}
                    </Badge>
                  ))}
                  {result.unused_variables.map((p) => (
                    <Badge key={`u-${p}`} variant="outline">
                      变量未用:{p}
                    </Badge>
                  ))}
                </div>
              )}
              <Label className="text-xs">渲染结果</Label>
              <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-md border bg-muted/30 p-3 text-xs leading-relaxed">
                {result.rendered}
              </pre>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
