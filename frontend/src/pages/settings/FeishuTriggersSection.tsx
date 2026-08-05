import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, RotateCcw, Save, Zap } from "lucide-react";

import {
  feishuTriggersApi,
  type FeishuMatchMode,
  type FeishuTriggerRule,
} from "@/api/feishuTriggers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";

type Draft = Record<
  string,
  { prefixesText: string; enabled: boolean; match_mode: FeishuMatchMode }
>;

function toDraft(items: FeishuTriggerRule[]): Draft {
  const out: Draft = {};
  for (const r of items) {
    out[r.action] = {
      prefixesText: r.prefixes.join(", "),
      enabled: r.enabled,
      match_mode: r.match_mode,
    };
  }
  return out;
}

function parsePrefixes(text: string): string[] {
  return text
    .split(/[,，\n]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

const MATCH_LABEL: Record<FeishuMatchMode, string> = {
  prefix: "前缀匹配",
  exact: "精确匹配",
};

export function FeishuTriggersSection() {
  const qc = useQueryClient();
  const listQ = useQuery({
    queryKey: ["feishu-triggers"],
    queryFn: () => feishuTriggersApi.list(),
  });
  const [draft, setDraft] = useState<Draft>({});

  useEffect(() => {
    if (listQ.data?.items) setDraft(toDraft(listQ.data.items));
  }, [listQ.data]);

  const save = useMutation({
    mutationFn: () => {
      const items = (listQ.data?.items ?? []).map((r) => {
        const d = draft[r.action];
        if (!d) return { action: r.action };
        return {
          action: r.action,
          prefixes: parsePrefixes(d.prefixesText),
          enabled: d.enabled,
          match_mode: d.match_mode,
        };
      });
      return feishuTriggersApi.update(items);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["feishu-triggers"] });
      toast.success("飞书触发前缀已保存");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const reset = useMutation({
    mutationFn: () => feishuTriggersApi.reset(),
    onSuccess: (res) => {
      setDraft(toDraft(res.items));
      qc.invalidateQueries({ queryKey: ["feishu-triggers"] });
      toast.success("已恢复默认触发前缀");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  function patch(action: string, patch: Partial<Draft[string]>) {
    setDraft((prev) => ({
      ...prev,
      [action]: { ...prev[action], ...patch },
    }));
  }

  if (listQ.isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        加载飞书触发配置…
      </div>
    );
  }

  const items = listQ.data?.items ?? [];

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="space-y-6 p-6">
          <div>
            <div className="flex items-center gap-2 text-lg font-semibold">
              <Zap className="h-5 w-5" />
              飞书触发前缀
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              配置各能力由哪些短语触发。「前缀匹配」表示消息后接正文（如学习总结）；
              「精确匹配」表示消息须与短语完全一致（如立即推题、帮助）。
            </p>
          </div>

          <div className="space-y-4">
            {items.map((rule) => {
              const d = draft[rule.action];
              if (!d) return null;
              return (
                <div
                  key={rule.action}
                  className="space-y-3 rounded-lg border p-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{rule.title}</span>
                        <Badge variant="outline">{MATCH_LABEL[d.match_mode]}</Badge>
                        <Badge variant="secondary" className="font-mono text-xs">
                          {rule.action}
                        </Badge>
                      </div>
                      {rule.description ? (
                        <p className="mt-1 text-xs text-muted-foreground">
                          {rule.description}
                        </p>
                      ) : null}
                    </div>
                    <label className="flex shrink-0 cursor-pointer items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={d.enabled}
                        onChange={(e) =>
                          patch(rule.action, { enabled: e.target.checked })
                        }
                        className="h-4 w-4 rounded border"
                      />
                      启用
                    </label>
                  </div>

                  <div className="space-y-2">
                    <Label>触发短语（逗号或换行分隔）</Label>
                    <Input
                      value={d.prefixesText}
                      onChange={(e) =>
                        patch(rule.action, { prefixesText: e.target.value })
                      }
                      placeholder={
                        d.match_mode === "prefix"
                          ? "总结, 学习总结, 笔记"
                          : "立即推题, 帮助"
                      }
                    />
                    {d.match_mode === "prefix" ? (
                      <p className="text-xs text-muted-foreground">
                        示例：发送「{parsePrefixes(d.prefixesText)[0] || "总结"}{" "}
                        今天学了…」触发 {rule.title}
                      </p>
                    ) : (
                      <p className="text-xs text-muted-foreground">
                        示例：发送「{parsePrefixes(d.prefixesText)[0] || "帮助"}」触发{" "}
                        {rule.title}
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="flex flex-wrap gap-2">
            <Button onClick={() => save.mutate()} disabled={save.isPending}>
              {save.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Save className="mr-2 h-4 w-4" />
              )}
              保存配置
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                if (window.confirm("确定恢复为系统默认触发前缀？")) reset.mutate();
              }}
              disabled={reset.isPending}
            >
              {reset.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <RotateCcw className="mr-2 h-4 w-4" />
              )}
              恢复默认
            </Button>
          </div>

          <p className="text-xs text-muted-foreground">
            「答案 12」「作答 15 …」等作答格式、复习卡片按钮回调不在此配置，由系统固定解析。
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
