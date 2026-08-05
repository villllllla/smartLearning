import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Link } from "react-router-dom";

import { ArrowLeft, CheckCircle2, FileText, Loader2 } from "lucide-react";



import { generationApi } from "@/api/generation";

import { Badge } from "@/components/ui/badge";

import { Button } from "@/components/ui/button";

import { Card, CardContent } from "@/components/ui/card";

import { Empty } from "@/components/Empty";

import { PageHeader } from "@/components/layout/PageHeader";

import { toast } from "@/components/ui/toast";

import { invalidateAfterCandidateCommit } from "@/lib/invalidateAfterCandidateCommit";

import { formatDateTime } from "@/lib/utils";



export function CandidateBatchesPage() {

  const qc = useQueryClient();

  const { data, isLoading } = useQuery({

    queryKey: ["candidate-batches"],

    queryFn: () => generationApi.listCandidateBatches(200),

  });



  const items = data ?? [];

  const orphanCount = items.filter((b) => !b.source_wiki_id).length;

  const totalCandidates = items.reduce((n, b) => n + b.count, 0);



  const bulkCommit = useMutation({

    mutationFn: (batchIds: string[]) =>

      generationApi.bulkCommitBatches({ batch_ids: batchIds, pick_all: true }),

    onSuccess: (res) => {

      invalidateAfterCandidateCommit(qc);

      const emptied = res.results.filter((r) => r.remaining === 0).length;

      toast.success(

        `批量入库完成：${res.total_saved} 道已入题库，${emptied}/${res.batches_done} 个批次已清空`,

      );

      if (res.total_remaining > 0) {

        toast.info(`仍有 ${res.total_remaining} 道未勾选，请打开对应批次继续处理`);

      }

    },

    onError: (e: Error) => toast.error(e.message),

  });



  const commitOne = useMutation({

    mutationFn: (batchId: string) =>

      generationApi.commitBatch(batchId, { pick_all: true }),

    onSuccess: (res, batchId) => {

      invalidateAfterCandidateCommit(qc, batchId);

      if (res.remaining > 0) {

        toast.success(`已入库 ${res.saved} 道，本批次仍剩 ${res.remaining} 道`);

        return;

      }

      toast.success(`已入库 ${res.saved} 道，该批次已移除`);

    },

    onError: (e: Error) => toast.error(e.message),

  });



  const runBulkCommit = () => {

    if (items.length === 0) return;

    const msg = `将把当前页 ${items.length} 个批次、共 ${totalCandidates} 道候选全部入库（跳过题库中已存在的重复题）。确定继续？`;

    if (!confirm(msg)) return;

    bulkCommit.mutate(items.map((b) => b.batch_id));

  };



  const committingBatchId = commitOne.isPending ? commitOne.variables : undefined;



  return (

    <>

      <PageHeader

        title="候选批次"

        description={

          isLoading

            ? "加载中…"

            : `共 ${items.length} 个批次 · 未关联文档 ${orphanCount} 个（文档页不显示，可在此查看）`

        }

        actions={

          <div className="flex flex-wrap items-center gap-2">

            <Button

              disabled={items.length === 0 || bulkCommit.isPending || commitOne.isPending}

              onClick={runBulkCommit}

            >

              {bulkCommit.isPending ? (

                <Loader2 className="h-4 w-4 animate-spin" />

              ) : (

                <CheckCircle2 className="h-4 w-4" />

              )}

              {bulkCommit.isPending

                ? "批量入库中…"

                : `批量入库全部 (${items.length})`}

            </Button>

            <Button variant="outline" asChild>

              <Link to="/bank">

                <ArrowLeft className="h-4 w-4" />

                返回题库

              </Link>

            </Button>

          </div>

        }

      />



      <div className="mx-auto max-w-3xl space-y-3 p-4 md:p-8">

        {orphanCount > 0 && (

          <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-900 dark:text-amber-200">

            部分历史候选未记录来源文档（source_wiki_id 为空），知识库列表上的「候选 N」可能对不上。

            请在本页按批次进入预览；重新生成面试题后会正确关联文档。

          </p>

        )}



        {!isLoading && items.length === 0 && (

          <Empty title="暂无候选批次" description="生成面试题后会出现于此。" />

        )}



        {items.map((b) => (

          <Card key={b.batch_id}>

            <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">

              <div className="min-w-0">

                <div className="flex flex-wrap items-center gap-2">

                  <span className="font-medium">{b.count} 道候选</span>

                  <span className="text-xs text-muted-foreground">

                    {formatDateTime(b.created_at)}

                  </span>

                  {!b.source_wiki_id && (

                    <Badge variant="outline" className="text-[10px]">

                      未关联文档

                    </Badge>

                  )}

                </div>

                {b.source_wiki_title ? (

                  <p className="mt-1 flex items-center gap-1 truncate text-sm text-muted-foreground">

                    <FileText className="h-3.5 w-3.5 shrink-0" />

                    <Link

                      to={`/wiki/${b.source_wiki_id}`}

                      className="truncate hover:text-foreground"

                    >

                      {b.source_wiki_title}

                    </Link>

                  </p>

                ) : (

                  <p className="mt-1 text-xs text-muted-foreground">

                    批次 {b.batch_id.slice(0, 8)}…

                  </p>

                )}

              </div>

              <div className="flex flex-wrap gap-2">

                <Button

                  variant="secondary"

                  size="sm"

                  disabled={bulkCommit.isPending || commitOne.isPending}

                  onClick={() => commitOne.mutate(b.batch_id)}

                >

                  {committingBatchId === b.batch_id ? (

                    <Loader2 className="h-4 w-4 animate-spin" />

                  ) : (

                    <CheckCircle2 className="h-4 w-4" />

                  )}

                  全部入库

                </Button>

                <Button variant="default" size="sm" asChild>

                  <Link

                    to={`/bank/candidates/${b.batch_id}`}

                    state={{ from: "batches" }}

                  >

                    打开预览

                  </Link>

                </Button>

              </div>

            </CardContent>

          </Card>

        ))}

      </div>

    </>

  );

}

