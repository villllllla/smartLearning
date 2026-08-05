import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { providersApi } from "@/api/providers";
import type { ProviderSummary } from "@/api/types";
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
import { Select } from "@/components/ui/select";
import { toast } from "@/components/ui/toast";

interface Props {
  open: boolean;
  provider?: ProviderSummary;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}

const TEMPLATES: Record<string, { base_url: string; hint: string }> = {
  openai_compatible: {
    base_url: "https://api.openai.com/v1",
    hint: "适配 OpenAI / DeepSeek / 通义 / 智谱等 OpenAI Chat Completions 协议",
  },
  ollama: {
    base_url: "http://localhost:11434",
    hint: "本地 Ollama,通常无需 API Key",
  },
  anthropic: {
    base_url: "https://api.anthropic.com",
    hint: "Anthropic Claude 官方接口",
  },
  custom: { base_url: "", hint: "自定义,只做 HEAD 请求探测" },
};

export function ProviderFormDialog({ open, provider, onOpenChange, onSaved }: Props) {
  const isEdit = !!provider;
  const [name, setName] = useState(provider?.name ?? "");
  const [type, setType] = useState(provider?.type ?? "openai_compatible");
  const [baseUrl, setBaseUrl] = useState(
    provider?.base_url ?? TEMPLATES["openai_compatible"]!.base_url,
  );
  const [apiKey, setApiKey] = useState("");
  const [enabled, setEnabled] = useState(provider?.enabled ?? false);

  // Keep baseUrl synced to template when type changes (for new providers only)
  useEffect(() => {
    if (!isEdit) {
      setBaseUrl(TEMPLATES[type]?.base_url ?? "");
    }
  }, [type, isEdit]);

  const { data: types } = useQuery({
    queryKey: ["provider-types"],
    queryFn: () => providersApi.types(),
  });

  const save = useMutation({
    mutationFn: async () => {
      if (isEdit && provider) {
        return providersApi.update(provider.id, {
          name,
          type,
          base_url: baseUrl,
          // empty string = keep existing key
          api_key: apiKey === "" ? "" : apiKey,
          enabled,
        });
      }
      return providersApi.create({
        name,
        type,
        base_url: baseUrl,
        api_key: apiKey || null,
        enabled,
      });
    },
    onSuccess: () => {
      toast.success(isEdit ? "已更新" : "已创建");
      onSaved();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? "编辑 Provider" : "新增 Provider"}</DialogTitle>
          <DialogDescription>
            API Key 服务端加密存储,前端仅显示掩码。
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4">
          <div className="grid gap-1.5">
            <Label htmlFor="prov-name">名称</Label>
            <Input
              id="prov-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例如:本地 Ollama / DeepSeek"
            />
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="prov-type">类型</Label>
            <Select
              id="prov-type"
              value={type}
              onChange={(e) => setType(e.target.value)}
            >
              {(types ?? Object.keys(TEMPLATES)).map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </Select>
            <p className="text-xs text-muted-foreground">
              {TEMPLATES[type]?.hint}
            </p>
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="prov-url">base_url</Label>
            <Input
              id="prov-url"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="http(s)://..."
            />
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="prov-key">API Key</Label>
            <Input
              id="prov-key"
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={
                isEdit
                  ? provider!.has_api_key
                    ? "留空 = 保留原 Key 不变"
                    : "尚未配置"
                  : "可选(本地 Ollama 不需要)"
              }
            />
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
            />
            启用此 Provider
          </label>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            onClick={() => save.mutate()}
            disabled={save.isPending || !name.trim()}
          >
            {save.isPending ? "保存中..." : "保存"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
