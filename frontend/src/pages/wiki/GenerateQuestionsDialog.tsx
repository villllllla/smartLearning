import { useEffect, useState } from "react";

import { useQueryClient } from "@tanstack/react-query";



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
import {

  getBulkGenerateState,

  isBulkGenerateBusy,

  startBulkGenerate,

  subscribeBulkGenerate,

} from "@/lib/bulkGenerateTask";

import { useSyncExternalStore } from "react";



interface Props {

  open: boolean;

  wikiId: number;

  wikiTitle: string;

  bankQuestionCount?: number;

  pendingCandidateCount?: number;

  onOpenChange: (open: boolean) => void;

}



type CountMode = "auto" | "fixed";



function useBulkTask() {

  return useSyncExternalStore(

    subscribeBulkGenerate,

    getBulkGenerateState,

    getBulkGenerateState,

  );

}



export function GenerateQuestionsDialog({

  open,

  wikiId,

  wikiTitle,

  bankQuestionCount = 0,

  pendingCandidateCount = 0,

  onOpenChange,

}: Props) {

  const qc = useQueryClient();

  const task = useBulkTask();

  const [mode, setMode] = useState<CountMode>("auto");

  const [n, setN] = useState(12);

  const [maxN, setMaxN] = useState(30);

  const [starting, setStarting] = useState(false);

  const hasPrior =

    bankQuestionCount > 0 || pendingCandidateCount > 0;

  const [replaceExisting, setReplaceExisting] = useState(hasPrior);



  const taskRunning = isBulkGenerateBusy();



  useEffect(() => {

    if (open) setReplaceExisting(hasPrior);

  }, [open, hasPrior]);



  const handleStart = async () => {

    setStarting(true);

    onOpenChange(false);

    await startBulkGenerate(

      {

        wiki_ids: [wikiId],

        wiki_titles: { [wikiId]: wikiTitle },

        n: mode === "auto" ? null : n,

        max_n: maxN,

        replace_existing: replaceExisting,

      },

      {

        onDone: () => {

          qc.invalidateQueries({ queryKey: ["wiki", wikiId] });

          qc.invalidateQueries({ queryKey: ["wiki-list"] });

        },

      },

    );

    setStarting(false);

  };



  return (

    <Dialog open={open} onOpenChange={onOpenChange}>

      <DialogContent>

        <DialogHeader>

          <DialogTitle>生成面试题</DialogTitle>

          <DialogDescription>

            将基于 wiki「{wikiTitle}」当前 main 分支的内容生成候选题。

            开始后可<strong>关闭本窗口</strong>，在页面<strong>底部进度条</strong>查看进度（与列表页批量生成相同）。

            生成会调用「设置 → Prompt 模板 → wiki_to_questions」当前版本与默认模型。

          </DialogDescription>

        </DialogHeader>



        {taskRunning && (

          <p className="rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-xs text-muted-foreground">

            当前有生成任务进行中（{task.completedWikis}/{task.totalWikis} 篇

            {task.pendingWikiCount > 0

              ? `，排队 ${task.pendingWikiCount} 篇`

              : ""}

            ）。可关闭此窗口，在底部查看进度；本篇若未在队列中将排队执行。

          </p>

        )}



        <div className="grid gap-4">

          <div className="grid gap-2">

            <Label>题量策略</Label>

            <div className="grid grid-cols-2 gap-2">

              <button

                type="button"

                onClick={() => setMode("auto")}

                disabled={starting}

                className={`rounded-md border px-3 py-2 text-sm text-left transition ${

                  mode === "auto"

                    ? "border-primary bg-primary/10 text-primary"

                    : "border-input hover:bg-muted"

                }`}

              >

                <div className="font-medium">由模型决定(推荐)</div>

                <div className="text-xs text-muted-foreground mt-0.5">

                  按内容信息密度自动出题

                </div>

              </button>

              <button

                type="button"

                onClick={() => setMode("fixed")}

                disabled={starting}

                className={`rounded-md border px-3 py-2 text-sm text-left transition ${

                  mode === "fixed"

                    ? "border-primary bg-primary/10 text-primary"

                    : "border-input hover:bg-muted"

                }`}

              >

                <div className="font-medium">固定题数</div>

                <div className="text-xs text-muted-foreground mt-0.5">

                  必须恰好生成 N 道

                </div>

              </button>

            </div>

          </div>



          {mode === "auto" ? (

            <div className="grid gap-1.5">

              <Label htmlFor="gen-max-n">上限保护</Label>

              <Input

                id="gen-max-n"

                type="number"

                min={3}

                max={50}

                value={maxN}

                disabled={starting}

                onChange={(e) => setMaxN(Number(e.target.value) || 30)}

              />

              <p className="text-xs text-muted-foreground">

                防止文档很长时模型一次性产出过多。下限固定 3 条;

                若文档信息不足,会少于下限,模型会被指示「宁可少出也不要凑数」。

              </p>

            </div>

          ) : (

            <div className="grid gap-1.5">

              <Label htmlFor="gen-n">生成题数</Label>

              <Input

                id="gen-n"

                type="number"

                min={1}

                max={50}

                value={n}

                disabled={starting}

                onChange={(e) => setN(Number(e.target.value) || 12)}

              />

              <p className="text-xs text-muted-foreground">

                PRD §6.3.2 推荐 12 道、八股 70% / 场景题 30%。

              </p>

            </div>

          )}



          {hasPrior && (

            <label className="flex cursor-pointer items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">

              <input

                type="checkbox"

                checked={replaceExisting}

                disabled={starting}

                onChange={(e) => setReplaceExisting(e.target.checked)}

                className="mt-0.5"

              />

              <span>

                本篇已入库 {bankQuestionCount} 题

                {pendingCandidateCount > 0

                  ? `、候选 ${pendingCandidateCount} 条`

                  : ""}

                。勾选后重新生成前会先删除这些题目。

              </span>

            </label>

          )}



          <div className="rounded-md border bg-muted/40 p-3 text-xs leading-relaxed text-muted-foreground">

            完成后可在底部进度条展开「查看各篇结果」进入候选预览页,可对每条单独勾选 / 编辑 / 丢弃,

            最后批量入库。入库时会冻结当前 prompt_template_id、model_id、source_commit_id,

            以保证可复现(PRD §6.3.3)。

          </div>

        </div>



        <DialogFooter>

          <Button

            variant="outline"

            onClick={() => onOpenChange(false)}

            disabled={starting}

          >

            {taskRunning ? "关闭" : "取消"}

          </Button>

          <Button onClick={() => void handleStart()} disabled={starting}>

            {starting

              ? "启动中…"

              : taskRunning

                ? "加入队列"

                : "开始生成"}

          </Button>

        </DialogFooter>

      </DialogContent>

    </Dialog>

  );

}


