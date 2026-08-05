import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { GitBranch, Loader2 } from "lucide-react";

import { branchApi, type BranchSummary } from "@/api/wiki";
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
  wikiId: number;
  branches: BranchSummary[];
  onOpenChange: (v: boolean) => void;
  onCreated: (branchId: number) => void;
}

export function NewBranchDialog({
  open,
  wikiId,
  branches,
  onOpenChange,
  onCreated,
}: Props) {
  const [name, setName] = useState("");
  const [baseId, setBaseId] = useState<string>(""); // empty = main

  const create = useMutation({
    mutationFn: () =>
      branchApi.create(wikiId, {
        name: name.trim(),
        base_branch_id: baseId === "" ? undefined : Number(baseId),
      }),
    onSuccess: (res) => {
      toast.success(`已创建分支 ${res.branch.name}`);
      onCreated(res.branch.id);
      onOpenChange(false);
      setName("");
      setBaseId("");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const valid = /^[A-Za-z0-9_\-./]{1,120}$/.test(name.trim()) && name.trim() !== "main";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <GitBranch className="h-4 w-4" />
            新建分支
          </DialogTitle>
          <DialogDescription>
            从已有分支拉一个新分支；新分支默认指向同一个 commit，第一次编辑后才会产生新提交。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="branch-name">分支名</Label>
            <Input
              id="branch-name"
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="feature/x · fix/typo · draft/2026-05"
            />
            <p className="text-[11px] text-muted-foreground">
              允许字母 / 数字 / <code>_ - . /</code>，长度 1–120；不可命名为 <code>main</code>。
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="branch-base">起点</Label>
            <Select
              id="branch-base"
              value={baseId}
              onChange={(e) => setBaseId(e.target.value)}
            >
              <option value="">main（默认）</option>
              {branches
                .filter((b) => b.name !== "main")
                .map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
            </Select>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            disabled={!valid || create.isPending}
            onClick={() => create.mutate()}
          >
            {create.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            创建
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
