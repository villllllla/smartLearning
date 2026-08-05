import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Pencil, Plus, Trash2 } from "lucide-react";

import { goalsApi, type JobRole, type UserGoal } from "@/api/goals";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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

const STATUS_LABELS: Record<UserGoal["status"], string> = {
  active: "进行中",
  achieved: "已达成",
  archived: "已归档",
};

const STATUS_VARIANT: Record<UserGoal["status"], "default" | "secondary" | "outline"> = {
  active: "default",
  achieved: "secondary",
  archived: "outline",
};

type FormState = {
  job_role_id: number | "";
  target_date: string;
  status: UserGoal["status"];
  clear_target_date: boolean;
};

const emptyForm = (): FormState => ({
  job_role_id: "",
  target_date: "",
  status: "active",
  clear_target_date: false,
});

export function GoalsManageTab({
  onViewProgress,
}: {
  onViewProgress: (goalId: number) => void;
}) {
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<UserGoal | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);

  const goalsQ = useQuery({
    queryKey: ["goals-list", statusFilter],
    queryFn: () => goalsApi.list(statusFilter || undefined),
  });
  const rolesQ = useQuery({ queryKey: ["job-roles"], queryFn: () => goalsApi.listJobRoles() });

  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: ["goals-list"] });
    qc.invalidateQueries({ queryKey: ["goals-active"] });
    qc.invalidateQueries({ queryKey: ["goal-progress"] });
  };

  const saveGoal = useMutation({
    mutationFn: async () => {
      if (form.job_role_id === "") throw new Error("请选择目标岗位");
      if (editing) {
        return goalsApi.update(editing.id, {
          job_role_id: Number(form.job_role_id),
          target_date: form.clear_target_date ? null : form.target_date || null,
          status: form.status,
          clear_target_date: form.clear_target_date,
        });
      }
      return goalsApi.create({
        job_role_id: Number(form.job_role_id),
        target_date: form.target_date || null,
      });
    },
    onSuccess: () => {
      invalidateAll();
      setDialogOpen(false);
      setEditing(null);
      toast.success(editing ? "目标已更新" : "目标已创建");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const deleteGoal = useMutation({
    mutationFn: (id: number) => goalsApi.remove(id),
    onSuccess: () => {
      invalidateAll();
      toast.success("目标已删除");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const setActive = useMutation({
    mutationFn: (id: number) => goalsApi.update(id, { status: "active" }),
    onSuccess: () => {
      invalidateAll();
      toast.success("已设为进行中");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const roles = rolesQ.data ?? [];
  const goals = goalsQ.data ?? [];

  const groupedRoles = useMemo(() => {
    const map = new Map<string, JobRole[]>();
    for (const r of roles) {
      const key = r.family || "其他";
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(r);
    }
    return map;
  }, [roles]);

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm());
    setDialogOpen(true);
  };

  const openEdit = (goal: UserGoal) => {
    setEditing(goal);
    setForm({
      job_role_id: goal.job_role_id,
      target_date: goal.target_date ?? "",
      status: goal.status,
      clear_target_date: false,
    });
    setDialogOpen(true);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Label className="sr-only">状态筛选</Label>
          <Select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="w-36"
          >
            <option value="">全部状态</option>
            <option value="active">进行中</option>
            <option value="achieved">已达成</option>
            <option value="archived">已归档</option>
          </Select>
        </div>
        <Button onClick={openCreate}>
          <Plus className="mr-2 h-4 w-4" />
          新建目标
        </Button>
      </div>

      {goalsQ.isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          加载目标列表…
        </div>
      ) : goals.length === 0 ? (
        <Card>
          <CardContent className="p-6 text-center text-sm text-muted-foreground">
            {statusFilter ? "没有符合筛选条件的目标" : "还没有求职目标，点击「新建目标」开始"}
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {goals.map((goal) => (
            <Card key={goal.id}>
              <CardContent className="flex flex-wrap items-start justify-between gap-4 p-4">
                <div className="min-w-0 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{goal.job_role_name}</span>
                    <Badge variant={STATUS_VARIANT[goal.status]}>
                      {STATUS_LABELS[goal.status]}
                    </Badge>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {goal.target_date ? `目标日期：${goal.target_date}` : "未设定目标日期"}
                    {" · "}
                    创建于 {new Date(goal.created_at).toLocaleDateString()}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" onClick={() => onViewProgress(goal.id)}>
                    查看进展
                  </Button>
                  {goal.status !== "active" ? (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={setActive.isPending}
                      onClick={() => setActive.mutate(goal.id)}
                    >
                      设为进行中
                    </Button>
                  ) : null}
                  <Button size="sm" variant="outline" onClick={() => openEdit(goal)}>
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={deleteGoal.isPending}
                    onClick={() => {
                      if (confirm(`确认删除目标「${goal.job_role_name}」？此操作不可恢复。`)) {
                        deleteGoal.mutate(goal.id);
                      }
                    }}
                  >
                    <Trash2 className="h-3.5 w-3.5 text-destructive" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing ? "编辑目标" : "新建目标"}</DialogTitle>
            <DialogDescription>
              {editing
                ? "修改岗位、目标日期或状态。设为「进行中」会自动归档其他进行中的目标。"
                : "新建目标会自动设为进行中，并归档之前的进行中目标。"}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label>目标岗位</Label>
              <Select
                value={form.job_role_id === "" ? "" : String(form.job_role_id)}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    job_role_id: e.target.value ? Number(e.target.value) : "",
                  }))
                }
              >
                <option value="">请选择…</option>
                {[...groupedRoles.entries()].map(([family, items]) => (
                  <optgroup key={family} label={family}>
                    {items.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.name}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </Select>
            </div>

            <div className="space-y-2">
              <Label>目标日期（可选）</Label>
              <Input
                type="date"
                value={form.target_date}
                disabled={form.clear_target_date}
                onChange={(e) => setForm((f) => ({ ...f, target_date: e.target.value }))}
              />
              {editing ? (
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={form.clear_target_date}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, clear_target_date: e.target.checked }))
                    }
                  />
                  清除目标日期
                </label>
              ) : null}
            </div>

            {editing ? (
              <div className="space-y-2">
                <Label>状态</Label>
                <Select
                  value={form.status}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      status: e.target.value as UserGoal["status"],
                    }))
                  }
                >
                  <option value="active">进行中</option>
                  <option value="achieved">已达成</option>
                  <option value="archived">已归档</option>
                </Select>
              </div>
            ) : null}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              取消
            </Button>
            <Button
              disabled={form.job_role_id === "" || saveGoal.isPending}
              onClick={() => saveGoal.mutate()}
            >
              {saveGoal.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              {editing ? "保存" : "创建"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
