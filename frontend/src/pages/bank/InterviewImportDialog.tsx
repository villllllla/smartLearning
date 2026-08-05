import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp, Loader2 } from "lucide-react";

import { bankApi } from "@/api/bank";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { toast } from "@/components/ui/toast";

export function InterviewImportDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  const jobQ = useQuery({
    queryKey: ["interview-answer-job", activeJobId],
    queryFn: () => bankApi.getInterviewAnswerJob(activeJobId!),
    enabled: !!activeJobId,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "queued" || s === "running" ? 3000 : false;
    },
  });

  useEffect(() => {
    if (!jobQ.data) return;
    if (jobQ.data.status === "completed" || jobQ.data.status === "failed") {
      qc.invalidateQueries({ queryKey: ["bank-questions"] });
      if (jobQ.data.status === "completed") {
        toast.success(
          `参考答案已生成 ${jobQ.data.completed_count}/${jobQ.data.total} 题` +
            (jobQ.data.failed_count ? `，${jobQ.data.failed_count} 题失败` : ""),
        );
      } else {
        toast.error(jobQ.data.last_error || "参考答案生成失败");
      }
      setActiveJobId(null);
    }
  }, [jobQ.data, qc]);

  const importM = useMutation({
    mutationFn: (list: File[]) => bankApi.importInterviewNotes(list),
    onSuccess: (res) => {
      setFiles([]);
      qc.invalidateQueries({ queryKey: ["bank-questions"] });
      qc.invalidateQueries({ queryKey: ["bank-tags"] });
      qc.invalidateQueries({ queryKey: ["interview-answer-jobs"] });
      toast.success(res.message);
      if (res.answer_job_id && res.answers_queued > 0) {
        setActiveJobId(res.answer_job_id);
      } else {
        onOpenChange(false);
      }
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const job = jobQ.data;
  const generating =
    !!activeJobId && job && (job.status === "queued" || job.status === "running");

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) {
          setFiles([]);
          setActiveJobId(null);
        }
        onOpenChange(v);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileUp className="h-5 w-5" />
            导入实战面经
          </DialogTitle>
          <DialogDescription>
            系统会解析以「？」结尾的问句入库，并按<strong>公司/轮次/主题</strong>将关联题打包排队，生成与模拟题库一致的标准参考答案。
          </DialogDescription>
        </DialogHeader>

        {!generating ? (
          <>
            <input
              ref={inputRef}
              type="file"
              accept=".md,text/markdown"
              multiple
              className="hidden"
              onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
            />
            <div className="rounded-md border border-dashed p-6 text-center text-sm">
              {files.length > 0 ? (
                <ul className="space-y-1 text-left">
                  {files.map((f) => (
                    <li key={f.name} className="truncate text-foreground">
                      {f.name}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-muted-foreground">支持 .md，可多选</p>
              )}
              <Button
                variant="outline"
                size="sm"
                className="mt-3"
                onClick={() => inputRef.current?.click()}
              >
                选择文件
              </Button>
            </div>
          </>
        ) : (
          <div className="rounded-md border bg-muted/30 p-4 text-sm">
            <div className="flex items-center gap-2 font-medium">
              <Loader2 className="h-4 w-4 animate-spin" />
              正在生成参考答案…
            </div>
            <p className="mt-2 text-muted-foreground">
              {job.doc_name} · {job.completed_count}/{job.total}
              {job.pack_count > 0 ? ` · ${job.pack_count} 个关联题组` : ""}
              {job.failed_count > 0 ? ` · 失败 ${job.failed_count}` : ""}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              同一公司/轮次的关联题会打包送入模型；题组过大时按组内顺序拆批，但不与其他项目混批。
            </p>
          </div>
        )}

        <DialogFooter>
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={importM.isPending}
          >
            {generating ? "后台继续" : "取消"}
          </Button>
          {!generating ? (
            <Button
              onClick={() => files.length && importM.mutate(files)}
              disabled={!files.length || importM.isPending}
            >
              {importM.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <FileUp className="mr-2 h-4 w-4" />
              )}
              解析并入库
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
