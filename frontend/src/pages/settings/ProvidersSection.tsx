import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plug, Plus, Trash2 } from "lucide-react";

import { providersApi } from "@/api/providers";
import { settingsApi } from "@/api/settings";
import type { ProviderSummary } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty } from "@/components/Empty";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { ProviderFormDialog } from "./ProviderFormDialog";
import { ModelFormDialog } from "./ModelFormDialog";
import { toast } from "@/components/ui/toast";

export function ProvidersSection() {
  const qc = useQueryClient();
  const [editing, setEditing] = useState<ProviderSummary | null>(null);
  const [creating, setCreating] = useState(false);
  const [addingModelTo, setAddingModelTo] = useState<ProviderSummary | null>(
    null,
  );

  const { data: providers, isLoading } = useQuery({
    queryKey: ["providers"],
    queryFn: () => providersApi.list(),
  });
  const settingsQ = useQuery({
    queryKey: ["settings"],
    queryFn: () => settingsApi.get(),
  });

  const allModels = (providers ?? []).flatMap((p) =>
    p.models.map((m) => ({
      id: m.id,
      name: m.name,
      provider: p.name,
      enabled: m.enabled && p.enabled,
    })),
  );

  const saveGlobalFallback = useMutation({
    mutationFn: (modelId: number | null) =>
      settingsApi.update(
        modelId == null
          ? { clear_llm_fallback_model: true }
          : { llm_fallback_model_id: modelId },
      ),
    onSuccess: () => {
      toast.success("全局兜底模型已保存");
      qc.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const remove = useMutation({
    mutationFn: (id: number) => providersApi.remove(id),
    onSuccess: () => {
      toast.success("已删除 Provider");
      qc.invalidateQueries({ queryKey: ["providers"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const probe = useMutation({
    mutationFn: (id: number) => providersApi.probe(id),
    onSuccess: (res) => {
      if (res.ok) {
        const timeoutHint =
          res.request_timeout_seconds != null && res.request_timeout_seconds > 0
            ? ` · 生成超时 ${res.request_timeout_seconds}s`
            : "";
        toast.success(`连通成功 · ${res.detail}${timeoutHint}`);
      } else {
        toast.error(`连通失败：${res.detail}`);
      }
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const removeModel = useMutation({
    mutationFn: ({ providerId, modelId }: { providerId: number; modelId: number }) =>
      providersApi.removeModel(providerId, modelId),
    onSuccess: () => {
      toast.success("已删除模型");
      qc.invalidateQueries({ queryKey: ["providers"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const items = providers ?? [];

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle>模型与 Provider</CardTitle>
          <p className="mt-1 text-xs text-muted-foreground">
            支持 openai_compatible(OpenAI / DeepSeek / 通义 / 智谱) · ollama(本地) · anthropic · custom。
            云端 Provider 默认关闭。
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <Plus className="h-4 w-4" />
          新增 Provider
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="rounded-lg border border-dashed bg-muted/20 p-4">
          <div className="text-sm font-medium">全局兜底模型</div>
          <p className="mt-1 text-xs text-muted-foreground">
            各功能场景的主模型与场景备用均失败后，最后尝试此模型（适用于 429/503/连接超时）。
          </p>
          <div className="mt-3 grid max-w-md gap-2">
            <Label>兜底模型</Label>
            <Select
              value={
                settingsQ.data?.llm_fallback_model_id != null
                  ? String(settingsQ.data.llm_fallback_model_id)
                  : ""
              }
              onChange={(e) => {
                const v = e.target.value;
                saveGlobalFallback.mutate(v === "" ? null : Number(v));
              }}
              disabled={saveGlobalFallback.isPending || settingsQ.isLoading}
            >
              <option value="">(不配置)</option>
              {allModels.map((m) => (
                <option key={m.id} value={m.id} disabled={!m.enabled}>
                  {m.name} · {m.provider}
                </option>
              ))}
            </Select>
          </div>
        </div>

        {isLoading && <div className="text-sm text-muted-foreground">加载中...</div>}
        {!isLoading && items.length === 0 && (
          <Empty
            title="还没有配置 Provider"
            description="先添加一个本地 Ollama 或云端 OpenAI 兼容服务,后续对话 / 生成 / 评分都依赖它。"
            action={
              <Button onClick={() => setCreating(true)}>
                <Plus className="h-4 w-4" />
                添加第一个
              </Button>
            }
          />
        )}

        {items.map((p) => (
          <div key={p.id} className="rounded-lg border bg-card p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="text-base font-semibold">{p.name}</span>
                <Badge variant="outline">{p.type}</Badge>
                {p.enabled ? (
                  <Badge variant="success">已启用</Badge>
                ) : (
                  <Badge variant="secondary">未启用</Badge>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => probe.mutate(p.id)}
                  disabled={probe.isPending}
                >
                  <Plug className="h-3.5 w-3.5" />
                  连通性测试
                </Button>
                <Button variant="outline" size="sm" onClick={() => setEditing(p)}>
                  编辑
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="删除"
                  onClick={() => {
                    if (confirm(`确认删除 Provider「${p.name}」?其下所有模型也会被删除。`)) {
                      remove.mutate(p.id);
                    }
                  }}
                >
                  <Trash2 className="h-4 w-4 text-muted-foreground hover:text-destructive" />
                </Button>
              </div>
            </div>

            <div className="mt-2 grid gap-1 text-xs text-muted-foreground sm:grid-cols-2">
              <div>
                base_url:
                <code className="ml-1 rounded bg-muted px-1.5 py-0.5 text-[11px]">
                  {p.base_url || "—"}
                </code>
              </div>
              <div>
                API Key:{" "}
                {p.has_api_key ? (
                  <code className="rounded bg-muted px-1.5 py-0.5 text-[11px]">
                    {p.masked_api_key}
                  </code>
                ) : (
                  <span className="text-amber-600">未配置</span>
                )}
              </div>
            </div>

            <div className="mt-4 border-t pt-3">
              <div className="mb-2 flex items-center justify-between">
                <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  模型({p.models.length})
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setAddingModelTo(p)}
                >
                  <Plus className="h-3.5 w-3.5" />
                  添加模型
                </Button>
              </div>

              {p.models.length === 0 ? (
                <div className="text-xs text-muted-foreground">
                  尚未添加模型。可手动添加,或先「连通性测试」自动发现可用模型。
                </div>
              ) : (
                <ul className="divide-y">
                  {p.models.map((m) => (
                    <li
                      key={m.id}
                      className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{m.name}</span>
                        {m.is_default && <Badge>默认</Badge>}
                        {m.supports_vision && (
                          <Badge variant="secondary">vision</Badge>
                        )}
                        {m.supports_streaming && (
                          <Badge variant="outline">stream</Badge>
                        )}
                        <span className="text-xs text-muted-foreground">
                          ctx {m.context_window}
                        </span>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          if (confirm(`删除模型「${m.name}」?`)) {
                            removeModel.mutate({
                              providerId: p.id,
                              modelId: m.id,
                            });
                          }
                        }}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        ))}
      </CardContent>

      {creating && (
        <ProviderFormDialog
          open={creating}
          onOpenChange={setCreating}
          onSaved={() =>
            qc.invalidateQueries({ queryKey: ["providers"] })
          }
        />
      )}
      {editing && (
        <ProviderFormDialog
          open={!!editing}
          provider={editing}
          onOpenChange={(o) => !o && setEditing(null)}
          onSaved={() => {
            setEditing(null);
            qc.invalidateQueries({ queryKey: ["providers"] });
          }}
        />
      )}
      {addingModelTo && (
        <ModelFormDialog
          open={!!addingModelTo}
          providerId={addingModelTo.id}
          onOpenChange={(o) => !o && setAddingModelTo(null)}
          onSaved={() => {
            setAddingModelTo(null);
            qc.invalidateQueries({ queryKey: ["providers"] });
          }}
        />
      )}
    </Card>
  );
}
