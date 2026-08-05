import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Copy, Eye, FilePlus2, Trash2 } from "lucide-react";

import { providersApi } from "@/api/providers";
import {
  type PromptTemplateSummary,
  type Scene,
  type SceneInfo,
  promptsApi,
} from "@/api/prompts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { toast } from "@/components/ui/toast";
import { cn, formatDateTime } from "@/lib/utils";
import { CreateVersionDialog } from "./CreateVersionDialog";
import { PreviewDialog } from "./PreviewDialog";

export function PromptsSection() {
  const qc = useQueryClient();
  const scenesQ = useQuery({
    queryKey: ["prompt-scenes"],
    queryFn: () => promptsApi.listScenes(),
  });
  const providersQ = useQuery({
    queryKey: ["providers"],
    queryFn: () => providersApi.list(),
  });

  const [activeScene, setActiveScene] = useState<Scene | null>(null);
  useEffect(() => {
    if (!activeScene && scenesQ.data && scenesQ.data.length > 0) {
      setActiveScene(scenesQ.data[0].scene);
    }
  }, [scenesQ.data, activeScene]);

  const [createDialog, setCreateDialog] = useState<
    | null
    | { scene: Scene; initialContent?: string; initialName?: string }
  >(null);
  const [previewDialog, setPreviewDialog] = useState<
    null | { scene: Scene; content: string }
  >(null);

  const setCurrent = useMutation({
    mutationFn: (versionId: number) => promptsApi.setCurrent(versionId),
    onSuccess: () => {
      toast.success("已设为当前生效版本");
      qc.invalidateQueries({ queryKey: ["prompt-scenes"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: (versionId: number) => promptsApi.deleteVersion(versionId),
    onSuccess: () => {
      toast.success("已删除");
      qc.invalidateQueries({ queryKey: ["prompt-scenes"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const allModels = useMemo(
    () =>
      (providersQ.data ?? []).flatMap((p) =>
        p.models.map((m) => ({
          id: m.id,
          name: m.name,
          provider: p.name,
          enabled: m.enabled && p.enabled,
        })),
      ),
    [providersQ.data],
  );

  if (scenesQ.isLoading) {
    return (
      <div className="text-sm text-muted-foreground">加载 Prompt 配置中...</div>
    );
  }
  if (scenesQ.error || !scenesQ.data) {
    return (
      <div className="text-sm text-destructive">
        加载失败:{(scenesQ.error as Error)?.message ?? "未知错误"}
      </div>
    );
  }

  const scenes = scenesQ.data;
  const current = scenes.find((s) => s.scene === activeScene) ?? scenes[0];

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground leading-relaxed">
        每个<strong>功能场景</strong>可单独配置<strong>主模型</strong>与<strong>备用模型</strong>。
        主模型失败（429/503/连接超时）时自动切换备用，再失败则使用「模型与 Provider」中的<strong>全局兜底模型</strong>。
        快速场景（如待办意图解析）建议选小模型；生成/评分类建议选大模型。
      </p>

      {/* Scene tabs */}
      <div className="flex flex-wrap gap-1.5 border-b">
        {scenes.map((s) => (
          <button
            key={s.scene}
            type="button"
            onClick={() => setActiveScene(s.scene)}
            className={cn(
              "border-b-2 px-3 py-2 text-sm transition-colors",
              s.scene === current.scene
                ? "border-primary font-medium text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {s.title}
            <span className="ml-1.5 text-[11px] text-muted-foreground">
              v{s.current_version_no ?? "?"}
            </span>
          </button>
        ))}
      </div>

      <SceneOverview
        scene={current}
        models={allModels}
        onChangeBinding={async (body) => {
          try {
            await promptsApi.updateBinding(current.scene, body);
            toast.success("已保存模型配置");
            qc.invalidateQueries({ queryKey: ["prompt-scenes"] });
          } catch (e) {
            toast.error((e as Error).message);
          }
        }}
        onCreateNew={() =>
          setCreateDialog({
            scene: current.scene,
            initialName: `${current.title} v${(current.current_version_no ?? 0) + 1}`,
            initialContent:
              current.versions.find((v) => v.is_current)?.content ?? "",
          })
        }
      />

      <div className="space-y-3">
        {current.versions.map((v) => (
          <VersionCard
            key={v.id}
            version={v}
            onSetCurrent={() => {
              if (v.is_current) return;
              setCurrent.mutate(v.id);
            }}
            onCopyToNew={() =>
              setCreateDialog({
                scene: current.scene,
                initialName: `${current.title} v${(current.current_version_no ?? v.version_no) + 1}`,
                initialContent: v.content,
              })
            }
            onPreview={() =>
              setPreviewDialog({ scene: current.scene, content: v.content })
            }
            onDelete={() => {
              if (
                confirm(
                  `删除 ${current.title} v${v.version_no}? 仅可删除非当前且未被引用的版本。`,
                )
              ) {
                remove.mutate(v.id);
              }
            }}
          />
        ))}
      </div>

      {createDialog && (
        <CreateVersionDialog
          open
          scene={createDialog.scene}
          initialName={createDialog.initialName}
          initialContent={createDialog.initialContent}
          onOpenChange={(o) => !o && setCreateDialog(null)}
          onCreated={() => {
            setCreateDialog(null);
            qc.invalidateQueries({ queryKey: ["prompt-scenes"] });
          }}
        />
      )}
      {previewDialog && (
        <PreviewDialog
          open
          scene={previewDialog.scene}
          content={previewDialog.content}
          onOpenChange={(o) => !o && setPreviewDialog(null)}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// SceneOverview: meta + binding (default model + params)
// ---------------------------------------------------------------------------

interface ModelOption {
  id: number;
  name: string;
  provider: string;
  enabled: boolean;
}

function SceneOverview({
  scene,
  models,
  onChangeBinding,
  onCreateNew,
}: {
  scene: SceneInfo;
  models: ModelOption[];
  onChangeBinding: (body: {
    model_id: number | null;
    fallback_model_id: number | null;
    params: Record<string, unknown>;
    fallback_params: Record<string, unknown>;
  }) => void | Promise<void>;
  onCreateNew: () => void;
}) {
  const [modelId, setModelId] = useState<number | null>(scene.binding_model_id);
  const [fallbackModelId, setFallbackModelId] = useState<number | null>(
    scene.binding_fallback_model_id,
  );
  const [temperature, setTemperature] = useState<string>(
    scene.binding_params.temperature !== undefined
      ? String(scene.binding_params.temperature)
      : "",
  );
  const [maxTokens, setMaxTokens] = useState<string>(
    scene.binding_params.max_tokens !== undefined
      ? String(scene.binding_params.max_tokens)
      : "",
  );
  const [fbTemperature, setFbTemperature] = useState<string>(
    scene.binding_fallback_params.temperature !== undefined
      ? String(scene.binding_fallback_params.temperature)
      : "",
  );
  const [fbMaxTokens, setFbMaxTokens] = useState<string>(
    scene.binding_fallback_params.max_tokens !== undefined
      ? String(scene.binding_fallback_params.max_tokens)
      : "",
  );

  useEffect(() => {
    setModelId(scene.binding_model_id);
    setFallbackModelId(scene.binding_fallback_model_id);
    setTemperature(
      scene.binding_params.temperature !== undefined
        ? String(scene.binding_params.temperature)
        : "",
    );
    setMaxTokens(
      scene.binding_params.max_tokens !== undefined
        ? String(scene.binding_params.max_tokens)
        : "",
    );
    setFbTemperature(
      scene.binding_fallback_params.temperature !== undefined
        ? String(scene.binding_fallback_params.temperature)
        : "",
    );
    setFbMaxTokens(
      scene.binding_fallback_params.max_tokens !== undefined
        ? String(scene.binding_fallback_params.max_tokens)
        : "",
    );
  }, [
    scene.scene,
    scene.binding_model_id,
    scene.binding_fallback_model_id,
    scene.binding_params,
    scene.binding_fallback_params,
  ]);

  const dirty =
    modelId !== scene.binding_model_id ||
    fallbackModelId !== scene.binding_fallback_model_id ||
    temperature !==
      (scene.binding_params.temperature !== undefined
        ? String(scene.binding_params.temperature)
        : "") ||
    maxTokens !==
      (scene.binding_params.max_tokens !== undefined
        ? String(scene.binding_params.max_tokens)
        : "") ||
    fbTemperature !==
      (scene.binding_fallback_params.temperature !== undefined
        ? String(scene.binding_fallback_params.temperature)
        : "") ||
    fbMaxTokens !==
      (scene.binding_fallback_params.max_tokens !== undefined
        ? String(scene.binding_fallback_params.max_tokens)
        : "");

  const buildParams = (temp: string, tokens: string): Record<string, unknown> | null => {
    const params: Record<string, unknown> = {};
    if (temp.trim() !== "") {
      const t = Number(temp);
      if (!Number.isFinite(t) || t < 0 || t > 2) {
        toast.error("temperature 应在 0–2 之间");
        return null;
      }
      params.temperature = t;
    }
    if (tokens.trim() !== "") {
      const m = Number(tokens);
      if (!Number.isInteger(m) || m <= 0) {
        toast.error("max_tokens 应为正整数");
        return null;
      }
      params.max_tokens = m;
    }
    return params;
  };

  const save = () => {
    const params = buildParams(temperature, maxTokens);
    if (params === null) return;
    const fallback_params = buildParams(fbTemperature, fbMaxTokens);
    if (fallback_params === null) return;
    onChangeBinding({
      model_id: modelId,
      fallback_model_id: fallbackModelId,
      params,
      fallback_params,
    });
  };

  const tierLabel =
    scene.model_tier === "fast"
      ? "快速响应"
      : scene.model_tier === "capable"
        ? "高质量"
        : null;

  return (
    <Card>
      <CardContent className="grid gap-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="text-base font-semibold">{scene.title}</div>
              {tierLabel ? <Badge variant="outline">{tierLabel}</Badge> : null}
            </div>
            <div className="mt-1 text-xs text-muted-foreground leading-relaxed">
              {scene.description}
            </div>
            {scene.model_hint ? (
              <p className="mt-1 text-xs text-primary/80">{scene.model_hint}</p>
            ) : null}
            {scene.placeholders.length > 0 && (
              <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
                <span className="text-muted-foreground">必须包含变量:</span>
                {scene.placeholders.map((p) => (
                  <code
                    key={p}
                    className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px]"
                  >
                    {p}
                  </code>
                ))}
              </div>
            )}
          </div>
          <Button onClick={onCreateNew} size="sm">
            <FilePlus2 className="h-4 w-4" />
            基于当前版本新建
          </Button>
        </div>

        <div className="grid gap-4 border-t pt-4 lg:grid-cols-2">
          <div className="space-y-3 rounded-md border p-3">
            <div className="text-sm font-medium">主模型</div>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="grid gap-1.5 sm:col-span-3">
                <Label>模型</Label>
                <Select
                  value={modelId === null ? "" : String(modelId)}
                  onChange={(e) =>
                    setModelId(e.target.value === "" ? null : Number(e.target.value))
                  }
                >
                  <option value="">(沿用全局默认)</option>
                  {models.map((m) => (
                    <option key={m.id} value={m.id} disabled={!m.enabled}>
                      {m.name} · {m.provider}
                      {!m.enabled ? "(已停用)" : ""}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="grid gap-1.5">
                <Label>temperature</Label>
                <Input
                  value={temperature}
                  onChange={(e) => setTemperature(e.target.value)}
                  placeholder="0.7"
                />
              </div>
              <div className="grid gap-1.5 sm:col-span-2">
                <Label>max_tokens</Label>
                <Input
                  value={maxTokens}
                  onChange={(e) => setMaxTokens(e.target.value)}
                  placeholder="1024"
                />
              </div>
            </div>
          </div>

          <div className="space-y-3 rounded-md border border-dashed p-3">
            <div className="text-sm font-medium">备用模型（场景兜底）</div>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="grid gap-1.5 sm:col-span-3">
                <Label>模型</Label>
                <Select
                  value={fallbackModelId === null ? "" : String(fallbackModelId)}
                  onChange={(e) =>
                    setFallbackModelId(
                      e.target.value === "" ? null : Number(e.target.value),
                    )
                  }
                >
                  <option value="">(不配置)</option>
                  {models.map((m) => (
                    <option key={m.id} value={m.id} disabled={!m.enabled}>
                      {m.name} · {m.provider}
                      {!m.enabled ? "(已停用)" : ""}
                    </option>
                  ))}
                </Select>
                <p className="text-[11px] text-muted-foreground">
                  主模型繁忙/不可用时自动切换；JSON 解析失败不会切换。
                </p>
              </div>
              <div className="grid gap-1.5">
                <Label>temperature</Label>
                <Input
                  value={fbTemperature}
                  onChange={(e) => setFbTemperature(e.target.value)}
                  placeholder="可选"
                />
              </div>
              <div className="grid gap-1.5 sm:col-span-2">
                <Label>max_tokens</Label>
                <Input
                  value={fbMaxTokens}
                  onChange={(e) => setFbMaxTokens(e.target.value)}
                  placeholder="可选"
                />
              </div>
            </div>
          </div>
        </div>

        <div className="flex justify-end">
          <Button onClick={save} disabled={!dirty} size="sm" variant="outline">
            保存模型配置
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// VersionCard
// ---------------------------------------------------------------------------

function VersionCard({
  version,
  onSetCurrent,
  onCopyToNew,
  onPreview,
  onDelete,
}: {
  version: PromptTemplateSummary;
  onSetCurrent: () => void;
  onCopyToNew: () => void;
  onPreview: () => void;
  onDelete: () => void;
}) {
  const [expanded, setExpanded] = useState(version.is_current);
  return (
    <Card className={cn(version.is_current && "ring-1 ring-primary/40")}>
      <CardContent className="space-y-2 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">v{version.version_no}</span>
              <span className="text-sm text-muted-foreground">·</span>
              <span className="text-sm">{version.name}</span>
              {version.is_current && (
                <Badge variant="success">
                  <CheckCircle2 className="h-3 w-3" />
                  当前生效
                </Badge>
              )}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              更新于 {formatDateTime(version.updated_at)}
              {version.notes && <> · {version.notes}</>}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" size="sm" onClick={onPreview} title="代入示例变量预览渲染">
              <Eye className="h-4 w-4" />
              预览
            </Button>
            <Button variant="ghost" size="sm" onClick={onCopyToNew} title="复制内容并创建新版本">
              <Copy className="h-4 w-4" />
              复制为新版
            </Button>
            {!version.is_current && (
              <Button variant="outline" size="sm" onClick={onSetCurrent}>
                设为当前
              </Button>
            )}
            {!version.is_current && (
              <Button
                variant="ghost"
                size="icon"
                aria-label="删除"
                onClick={onDelete}
                title="非当前且未被引用的版本可删除"
              >
                <Trash2 className="h-4 w-4 text-muted-foreground hover:text-destructive" />
              </Button>
            )}
          </div>
        </div>

        <Button
          variant="link"
          size="sm"
          onClick={() => setExpanded((p) => !p)}
        >
          {expanded ? "收起内容" : "查看内容"}
        </Button>

        {expanded && (
          <pre className="whitespace-pre-wrap rounded-md border bg-muted/30 p-3 text-xs leading-relaxed">
            {version.content}
          </pre>
        )}
      </CardContent>
    </Card>
  );
}
