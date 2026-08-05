import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Loader2, Play, Target } from "lucide-react";

import { goalsApi } from "@/api/goals";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { setPracticeSession } from "@/pages/practice/session";

import { MasteryBar } from "./MasteryBar";

export function GoalsOverviewTab({
  focusGoalId,
  onClearFocus,
  onGoManage,
}: {
  focusGoalId: number | null;
  onClearFocus: () => void;
  onGoManage: () => void;
}) {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const activeQ = useQuery({ queryKey: ["goals-active"], queryFn: () => goalsApi.getActive() });
  const focusQ = useQuery({
    queryKey: ["goal-detail", focusGoalId],
    queryFn: () => goalsApi.get(focusGoalId!),
    enabled: focusGoalId != null,
  });

  const displayGoal = focusGoalId != null ? focusQ.data : activeQ.data;
  const goalId = displayGoal?.id;

  const progressQ = useQuery({
    queryKey: ["goal-progress", goalId],
    queryFn: () => goalsApi.progress(goalId!),
    enabled: !!goalId,
  });

  const practiceWeak = useMutation({
    mutationFn: () => goalsApi.recommendPractice(goalId!),
    onSuccess: (res) => {
      if (res.questions.length === 0) {
        toast.error("弱项暂无可用题目，请先生成/入库带对应标签的题");
        return;
      }
      setPracticeSession({
        questions: res.questions,
        answers: {},
        timeLimit: res.time_limit_per_question,
        startedAt: Date.now(),
      });
      navigate("/practice/run");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const progress = progressQ.data;
  const isViewingHistorical = focusGoalId != null && activeQ.data?.id !== focusGoalId;

  if (!displayGoal && !activeQ.isLoading && !focusQ.isLoading) {
    return (
      <Card>
        <CardContent className="space-y-4 p-6 text-center">
          <div className="flex items-center justify-center gap-2 text-lg font-semibold">
            <Target className="h-5 w-5 text-primary" />
            暂无进行中的目标
          </div>
          <p className="text-sm text-muted-foreground">
            在「目标管理」中新建目标，或将已有目标设为进行中，即可在此查看掌握度与弱项。
          </p>
          <Button onClick={onGoManage}>去管理目标</Button>
        </CardContent>
      </Card>
    );
  }

  if ((activeQ.isLoading || focusQ.isLoading) && !displayGoal) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        加载目标…
      </div>
    );
  }

  if (!displayGoal) return null;

  return (
    <div className="space-y-6">
      {isViewingHistorical ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border bg-muted/40 px-3 py-2 text-sm">
          <span>
            正在查看
            <Badge variant="outline" className="mx-2">
              {displayGoal.status === "active"
                ? "进行中"
                : displayGoal.status === "achieved"
                  ? "已达成"
                  : "已归档"}
            </Badge>
            目标的历史进展
          </span>
          <Button size="sm" variant="outline" onClick={onClearFocus}>
            返回当前进行中
          </Button>
        </div>
      ) : null}

      <Card>
        <CardContent className="space-y-4 p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-lg font-semibold">{displayGoal.job_role_name}</div>
              {displayGoal.target_date ? (
                <div className="text-sm text-muted-foreground">
                  目标日期：{displayGoal.target_date}
                </div>
              ) : null}
            </div>
            {progress ? (
              <div className="text-right">
                <div className="text-3xl font-bold text-primary">{progress.overall_mastery}%</div>
                <div className="text-xs text-muted-foreground">整体掌握度</div>
              </div>
            ) : null}
          </div>

          {progress?.coverage_note ? (
            <p className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-200">
              {progress.coverage_note}
            </p>
          ) : null}

          {progressQ.isLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              计算进展…
            </div>
          ) : progress ? (
            <div className="space-y-4">
              {progress.skills.map((s) => (
                <MasteryBar
                  key={s.tag_name}
                  label={s.skill_name}
                  mastery={s.mastery}
                  expected={s.expected_mastery}
                  coverage={s.coverage}
                  lowCoverage={s.low_coverage}
                />
              ))}
            </div>
          ) : null}

          {progress && progress.weak_tags.length > 0 ? (
            <div className="space-y-2">
              <Label>弱项清单</Label>
              <div className="flex flex-wrap gap-2">
                {progress.weak_tags.map((w) => (
                  <Badge key={w.tag_name} variant="outline">
                    {w.tag_name} · 差距 {w.gap}%
                  </Badge>
                ))}
              </div>
            </div>
          ) : null}

          {displayGoal.status === "active" ? (
            <div className="flex flex-wrap gap-2 pt-2">
              <Button
                onClick={() => practiceWeak.mutate()}
                disabled={practiceWeak.isPending || !progress}
              >
                {practiceWeak.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Play className="mr-2 h-4 w-4" />
                )}
                弱项专项练习
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  qc.invalidateQueries({ queryKey: ["goal-progress"] });
                  progressQ.refetch();
                }}
              >
                刷新进展
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {progress && progress.trend.length > 1 ? (
        <Card>
          <CardContent className="p-6">
            <Label className="mb-3 block">近期趋势</Label>
            <div className="flex h-24 items-end gap-1">
              {progress.trend.map((p) => (
                <div
                  key={p.computed_at}
                  className="flex-1 rounded-t bg-primary/70"
                  style={{ height: `${Math.max(8, p.overall_mastery)}%` }}
                  title={`${new Date(p.computed_at).toLocaleString()} · ${p.overall_mastery}%`}
                />
              ))}
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
