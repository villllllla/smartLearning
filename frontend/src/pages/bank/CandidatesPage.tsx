import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Trash2,
} from "lucide-react";

import {
  generationApi,
  type CandidatePayload,
  type CandidateSummary,
} from "@/api/generation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Empty } from "@/components/Empty";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/layout/PageHeader";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/components/ui/toast";
import { invalidateAfterCandidateCommit } from "@/lib/invalidateAfterCandidateCommit";
import { cn } from "@/lib/utils";

export function CandidatesPage() {
  const { batchId } = useParams<{ batchId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const fromBatches = (location.state as { from?: string } | null)?.from === "batches";
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["candidates", batchId],
    queryFn: () => generationApi.listCandidates(batchId ?? ""),
    enabled: !!batchId,
  });

  const [expanded, setExpanded] = useState<Record<number, boolean>>({});

  const update = useMutation({
    mutationFn: (vars: { id: number; payload?: CandidatePayload; picked?: boolean }) =>
      generationApi.updateCandidate(vars.id, {
        payload_json: vars.payload,
        picked: vars.picked,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["candidates", batchId] }),
    onError: (e: Error) => toast.error(e.message),
  });

  const discard = useMutation({
    mutationFn: (id: number) => generationApi.discardCandidate(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["candidates", batchId] });
      toast.info("已丢弃");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const commit = useMutation({
    mutationFn: (pickAll: boolean) =>
      generationApi.commitBatch(batchId ?? "", { pick_all: pickAll }),
    onSuccess: (res, pickAll) => {
      invalidateAfterCandidateCommit(qc, batchId);
      if (res.remaining > 0) {
        toast.success(
          `已入库 ${res.saved} 道，本批次仍剩 ${res.remaining} 道未勾选（可继续处理或丢弃）`,
        );
        return;
      }
      toast.success(
        pickAll
          ? `已全部入库 ${res.saved} 道，该批次已从候选列表移除`
          : `已入库 ${res.saved} 道，该批次已从候选列表移除`,
      );
      navigate(fromBatches ? "/bank/candidate-batches" : "/bank");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const items = data ?? [];
  const pickedCount = useMemo(() => items.filter((c) => c.picked).length, [items]);

  const toggleAll = (picked: boolean) => {
    for (const c of items) {
      if (c.picked !== picked) update.mutate({ id: c.id, picked });
    }
  };

  return (
    <>
      <PageHeader
        title="候选题预览"
        description={
          isLoading
            ? "加载候选..."
            : `批次 ${batchId?.slice(0, 8)}… · 本页 ${items.length} 道（与文档「查看候选」一致）· 已勾选 ${pickedCount}`
        }
        actions={
          <>
            <Button variant="outline" asChild>
              <Link to={fromBatches ? "/bank/candidate-batches" : "/wiki"}>
                <ArrowLeft className="h-4 w-4" />
                {fromBatches ? "返回候选批次" : "返回知识库"}
              </Link>
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => toggleAll(true)}
              disabled={items.length === 0}
            >
              全选
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => toggleAll(false)}
              disabled={items.length === 0}
            >
              全不选
            </Button>
            <Button
              variant="secondary"
              onClick={() => commit.mutate(true)}
              disabled={items.length === 0 || commit.isPending}
            >
              <CheckCircle2 className="h-4 w-4" />
              {commit.isPending ? "入库中..." : `全部入库 (${items.length})`}
            </Button>
            <Button
              onClick={() => commit.mutate(false)}
              disabled={pickedCount === 0 || commit.isPending}
            >
              <CheckCircle2 className="h-4 w-4" />
              {commit.isPending ? "入库中..." : `入库已勾选 (${pickedCount})`}
            </Button>
          </>
        }
      />

      <div className="mx-auto max-w-4xl space-y-3 p-4 md:p-8">
        {!isLoading && items.length === 0 && (
          <Empty
            title="批次为空"
            description="该批次的候选题已被清空(可能已全部入库或丢弃)。回知识库重新生成即可。"
          />
        )}
        {items.map((cand) => (
          <CandidateCard
            key={cand.id}
            cand={cand}
            expanded={!!expanded[cand.id]}
            onToggleExpand={() =>
              setExpanded((prev) => ({ ...prev, [cand.id]: !prev[cand.id] }))
            }
            onTogglePick={(picked) => update.mutate({ id: cand.id, picked })}
            onSavePayload={(payload) => update.mutate({ id: cand.id, payload })}
            onDiscard={() => {
              if (confirm("丢弃这条候选题?(不可恢复)")) discard.mutate(cand.id);
            }}
          />
        ))}
      </div>
    </>
  );
}

interface CardProps {
  cand: CandidateSummary;
  expanded: boolean;
  onToggleExpand: () => void;
  onTogglePick: (picked: boolean) => void;
  onSavePayload: (payload: CandidatePayload) => void;
  onDiscard: () => void;
}

function CandidateCard({
  cand,
  expanded,
  onToggleExpand,
  onTogglePick,
  onSavePayload,
  onDiscard,
}: CardProps) {
  const [draft, setDraft] = useState<CandidatePayload>(() => ({
    ...cand.payload_json,
    tag: [...(cand.payload_json.tag ?? [])],
  }));
  const [tagText, setTagText] = useState(
    (cand.payload_json.tag ?? []).join(", "),
  );

  // Re-sync draft when underlying cand changes (e.g. after server update)
  useEffect(() => {
    setDraft({ ...cand.payload_json, tag: [...(cand.payload_json.tag ?? [])] });
    setTagText((cand.payload_json.tag ?? []).join(", "));
  }, [cand.payload_json]);

  const dirty = useMemo(() => {
    const a = JSON.stringify({ ...cand.payload_json, tag: cand.payload_json.tag ?? [] });
    const b = JSON.stringify({
      ...draft,
      tag: tagText
        .split(/[,，]/)
        .map((s) => s.trim())
        .filter(Boolean),
    });
    return a !== b;
  }, [draft, tagText, cand.payload_json]);

  const save = () => {
    const tag = tagText
      .split(/[,，]/)
      .map((s) => s.trim())
      .filter(Boolean);
    onSavePayload({ ...draft, tag });
  };

  return (
    <Card className={cn(cand.picked && "ring-2 ring-primary/40")}>
      <CardContent className="p-4">
        <div className="flex items-start gap-3">
          <input
            type="checkbox"
            checked={cand.picked}
            onChange={(e) => onTogglePick(e.target.checked)}
            className="mt-1.5 h-4 w-4 cursor-pointer"
            aria-label="选中此候选"
          />
          <button
            type="button"
            onClick={onToggleExpand}
            className="mt-1 text-muted-foreground hover:text-foreground"
            aria-label={expanded ? "收起" : "展开"}
          >
            {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </button>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-base font-medium leading-snug">
                {cand.payload_json.question || "(空题干)"}
              </span>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Badge variant={difficultyVariant(cand.payload_json.difficulty)}>
                {cand.payload_json.difficulty}
              </Badge>
              <Badge variant="outline">{cand.payload_json.type}</Badge>
              {(cand.payload_json.tag ?? []).map((t) => (
                <Badge key={t} variant="secondary">
                  {t}
                </Badge>
              ))}
              {cand.edited && <Badge variant="warning">已编辑</Badge>}
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon"
            aria-label="丢弃"
            onClick={onDiscard}
          >
            <Trash2 className="h-4 w-4 text-muted-foreground hover:text-destructive" />
          </Button>
        </div>

        {expanded && (
          <div className="mt-4 grid gap-3 border-t pt-4">
            <div className="grid gap-1.5">
              <Label htmlFor={`q-${cand.id}`}>题干</Label>
              <Textarea
                id={`q-${cand.id}`}
                value={draft.question}
                onChange={(e) => setDraft({ ...draft, question: e.target.value })}
                rows={2}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor={`a-${cand.id}`}>标准答案</Label>
              <Textarea
                id={`a-${cand.id}`}
                value={draft.answer}
                onChange={(e) => setDraft({ ...draft, answer: e.target.value })}
                rows={5}
              />
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="grid gap-1.5">
                <Label htmlFor={`d-${cand.id}`}>难度</Label>
                <Select
                  id={`d-${cand.id}`}
                  value={draft.difficulty}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      difficulty: e.target.value as CandidatePayload["difficulty"],
                    })
                  }
                >
                  <option value="easy">easy</option>
                  <option value="medium">medium</option>
                  <option value="hard">hard</option>
                </Select>
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor={`t-${cand.id}`}>类型</Label>
                <Select
                  id={`t-${cand.id}`}
                  value={draft.type}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      type: e.target.value as CandidatePayload["type"],
                    })
                  }
                >
                  <option value="concept">concept(八股)</option>
                  <option value="scenario">scenario(场景)</option>
                </Select>
              </div>
              <div className="grid gap-1.5 sm:col-span-1">
                <Label htmlFor={`tag-${cand.id}`}>标签(逗号分隔)</Label>
                <Input
                  id={`tag-${cand.id}`}
                  value={tagText}
                  onChange={(e) => setTagText(e.target.value)}
                  placeholder="如:体系化, JVM"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="ghost" size="sm" onClick={() => onToggleExpand()}>
                收起
              </Button>
              <Button size="sm" onClick={save} disabled={!dirty}>
                保存修改
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function difficultyVariant(d: string) {
  if (d === "easy") return "success" as const;
  if (d === "hard") return "destructive" as const;
  return "default" as const;
}
