import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { providersApi } from "@/api/providers";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";

interface Props {
  open: boolean;
  providerId: number;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}

export function ModelFormDialog({
  open,
  providerId,
  onOpenChange,
  onSaved,
}: Props) {
  const [name, setName] = useState("");
  const [contextWindow, setContextWindow] = useState(8192);
  const [vision, setVision] = useState(false);
  const [streaming, setStreaming] = useState(true);
  const [isDefault, setIsDefault] = useState(false);

  const save = useMutation({
    mutationFn: () =>
      providersApi.addModel(providerId, {
        name: name.trim(),
        context_window: contextWindow,
        supports_vision: vision,
        supports_streaming: streaming,
        is_default: isDefault,
      }),
    onSuccess: () => {
      toast.success("已添加模型");
      onSaved();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>添加模型</DialogTitle>
        </DialogHeader>

        <div className="grid gap-4">
          <div className="grid gap-1.5">
            <Label htmlFor="model-name">模型名称</Label>
            <Input
              id="model-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例如:gpt-4o-mini / qwen2.5:7b / claude-3-5-sonnet-latest"
            />
            <p className="text-xs text-muted-foreground">
              这里是调用模型时的标识符,需要与 Provider 一致。
            </p>
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="model-ctx">上下文窗口</Label>
            <Input
              id="model-ctx"
              type="number"
              min={512}
              value={contextWindow}
              onChange={(e) => setContextWindow(Number(e.target.value) || 0)}
            />
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={vision}
              onChange={(e) => setVision(e.target.checked)}
            />
            支持图片输入(vision)
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={streaming}
              onChange={(e) => setStreaming(e.target.checked)}
            />
            支持流式输出
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={isDefault}
              onChange={(e) => setIsDefault(e.target.checked)}
            />
            设为默认模型(全局唯一)
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
            {save.isPending ? "保存中..." : "添加"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
