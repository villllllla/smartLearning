import { useEffect, useMemo, useState } from "react";

import { useSyncExternalStore } from "react";

import { Loader2 } from "lucide-react";



import type { WikiSummary } from "@/api/types";

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



interface Props {

  open: boolean;

  wikis: WikiSummary[];

  onOpenChange: (open: boolean) => void;

  onDone?: () => void;

}



type CountMode = "auto" | "fixed";



function useBulkGenerateTask() {

  return useSyncExternalStore(

    subscribeBulkGenerate,

    getBulkGenerateState,

    getBulkGenerateState,

  );

}



export function BulkGenerateQuestionsDialog({

  open,

  wikis,

  onOpenChange,

  onDone,

}: Props) {

  const task = useBulkGenerateTask();

  const [mode, setMode] = useState<CountMode>("auto");

  const [n, setN] = useState(12);

  const [maxN, setMaxN] = useState(30);

  const [replaceExisting, setReplaceExisting] = useState(true);

  const [starting, setStarting] = useState(false);



  const batchCount = Math.max(1, Math.ceil(wikis.length / 5));

  const taskRunning = isBulkGenerateBusy();



  const anyHasQuestions = useMemo(

    () =>

      wikis.some(

        (w) => (w.bank_question_count ?? 0) > 0 || (w.pending_candidate_count ?? 0) > 0,

      ),

    [wikis],

  );

  const noMainContentCount = useMemo(

    () => wikis.filter((w) => w.current_main_commit_id == null).length,

    [wikis],

  );



  useEffect(() => {

    if (!open) return;

    setReplaceExisting(anyHasQuestions);

  }, [open, anyHasQuestions]);



  const handleStart = async () => {

    setStarting(true);

    const wiki_titles = Object.fromEntries(wikis.map((w) => [w.id, w.title]));

    onOpenChange(false);

    await startBulkGenerate(

      {

        wiki_ids: wikis.map((w) => w.id),

        wiki_titles,

        n: mode === "auto" ? null : n,

        max_n: maxN,

        replace_existing: replaceExisting,

      },

      { onDone },

    );

    setStarting(false);

  };



  return (

    <Dialog open={open} onOpenChange={onOpenChange}>

      <DialogContent className="max-h-[90vh] max-w-lg overflow-y-auto">

        <DialogHeader>

          <DialogTitle>批量生成面试题</DialogTitle>

          <DialogDescription>

            已选 {wikis.length} 篇。生成在浏览器内<strong>按批顺序请求</strong>（每批最多 5

            篇）。开始后可<strong>关闭本窗口</strong>并继续勾选其他文档，点「加入队列」排队；底部进度条显示进度，可最小化到右下角。

            {wikis.length > 5 ? " 超过 5 篇将分多批请求。" : ""}

          </DialogDescription>

        </DialogHeader>

        {noMainContentCount > 0 && (

          <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-900 dark:text-amber-200">

            {noMainContentCount} 篇尚无 main 正文（未上传或未 Obsidian 同步），批量生成会直接失败。请先在「设置 →

            数据与外观」执行 Obsidian 全量同步，或单独上传 .md。

          </p>

        )}



        {taskRunning && (

          <p className="rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-xs text-muted-foreground">

            当前有任务进行中（{task.completedWikis}/{task.totalWikis} 篇
            {task.pendingWikiCount > 0 ? `，排队 ${task.pendingWikiCount} 篇` : ""}
            ）。未在队列中的文档可点「加入队列」；可关闭此窗口继续浏览。

          </p>

        )}



        <ul className="max-h-40 space-y-1 overflow-y-auto rounded-md border bg-muted/30 p-2 text-xs">

          {wikis.map((w) => (

            <li key={w.id} className="flex justify-between gap-2">

              <span className="truncate font-medium">{w.title}</span>

              <span className="shrink-0 text-muted-foreground">

                {(w.bank_question_count ?? 0) > 0

                  ? `已入库 ${w.bank_question_count}`

                  : "未出题"}

                {(w.pending_candidate_count ?? 0) > 0

                  ? ` · 候选 ${w.pending_candidate_count}`

                  : ""}

              </span>

            </li>

          ))}

        </ul>



        <div className="grid gap-4">

          <div className="grid gap-2">

            <Label>题量策略</Label>

            <div className="grid grid-cols-2 gap-2">

              <button

                type="button"

                onClick={() => setMode("auto")}

                disabled={taskRunning || starting}

                className={`rounded-md border px-3 py-2 text-left text-sm transition ${

                  mode === "auto"

                    ? "border-primary bg-primary/10 text-primary"

                    : "border-input hover:bg-muted"

                }`}

              >

                <div className="font-medium">由模型决定</div>

              </button>

              <button

                type="button"

                onClick={() => setMode("fixed")}

                disabled={taskRunning || starting}

                className={`rounded-md border px-3 py-2 text-left text-sm transition ${

                  mode === "fixed"

                    ? "border-primary bg-primary/10 text-primary"

                    : "border-input hover:bg-muted"

                }`}

              >

                <div className="font-medium">固定题数</div>

              </button>

            </div>

          </div>



          {mode === "auto" ? (

            <div className="grid gap-1.5">

              <Label htmlFor="bulk-max-n">上限保护</Label>

              <Input

                id="bulk-max-n"

                type="number"

                min={3}

                max={50}

                value={maxN}

                disabled={taskRunning || starting}

                onChange={(e) => setMaxN(Number(e.target.value) || 30)}

              />

            </div>

          ) : (

            <div className="grid gap-1.5">

              <Label htmlFor="bulk-n">每篇题数</Label>

              <Input

                id="bulk-n"

                type="number"

                min={1}

                max={50}

                value={n}

                disabled={taskRunning || starting}

                onChange={(e) => setN(Number(e.target.value) || 12)}

              />

            </div>

          )}



          {anyHasQuestions && (

            <label className="flex cursor-pointer items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">

              <input

                type="checkbox"

                checked={replaceExisting}

                disabled={taskRunning || starting}

                onChange={(e) => setReplaceExisting(e.target.checked)}

                className="mt-0.5"

              />

              <span>

                重新生成前删除已有题目(含已入库与未提交候选)。

                取消勾选则保留旧题并追加新候选(可能重复)。

              </span>

            </label>

          )}

        </div>



        <DialogFooter>

          <Button variant="outline" onClick={() => onOpenChange(false)}>

            {taskRunning ? "关闭" : "取消"}

          </Button>

          <Button

            onClick={() => void handleStart()}

            disabled={starting || wikis.length === 0}

          >

            {starting ? (

              <>

                <Loader2 className="mr-2 h-4 w-4 animate-spin" />

                启动中…

              </>

            ) : taskRunning ? (

              <>

                加入队列

                {batchCount > 1 ? `（${batchCount} 批）` : ""}

              </>

            ) : (

              <>

                开始生成

                {batchCount > 1 ? `（${batchCount} 批）` : ""}

              </>

            )}

          </Button>

        </DialogFooter>

      </DialogContent>

    </Dialog>

  );

}


