import { useCallback, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  Archive,
  CheckCircle2,
  FileText,
  Upload,
  XCircle,
} from "lucide-react";

import { wikiApi } from "@/api/wiki";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PageHeader } from "@/components/layout/PageHeader";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import type { UploadResponse } from "@/api/types";

const ACCEPT = ".md,.markdown,.zip,text/markdown,application/zip";
const ACCEPT_RE = /\.(md|markdown|zip)$/i;

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function WikiUploadPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [result, setResult] = useState<UploadResponse | null>(null);

  const upload = useMutation({
    mutationFn: (fs: File[]) => wikiApi.upload(fs),
    onSuccess: (res) => {
      setResult(res);
      qc.invalidateQueries({ queryKey: ["wiki-list"] });
      if (res.created > 0) {
        toast.success(`成功导入 ${res.created} 篇,失败 ${res.failed} 篇`);
      } else {
        toast.error(`全部失败,共 ${res.failed} 篇`);
      }
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const addFiles = useCallback((fs: FileList | File[]) => {
    const all = Array.from(fs);
    const arr = all.filter((f) => ACCEPT_RE.test(f.name));
    if (arr.length !== all.length) {
      toast.info("已忽略非 .md / .markdown / .zip 文件");
    }
    setFiles((prev) => {
      const seen = new Set(prev.map((p) => `${p.name}:${p.size}`));
      const merged = [...prev];
      for (const f of arr) {
        const k = `${f.name}:${f.size}`;
        if (!seen.has(k)) {
          merged.push(f);
          seen.add(k);
        }
      }
      return merged;
    });
  }, []);

  return (
    <>
      <PageHeader
        title="上传 Markdown / Zip 包"
        description="单纯 .md 直接传;若 md 里有图片,把 md + 同目录资产打成 .zip 一起传,系统会自动提取并重写链接"
        actions={
          <Button variant="outline" onClick={() => navigate("/wiki")}>
            返回列表
          </Button>
        }
      />

      <div className="mx-auto max-w-3xl space-y-6 p-4 md:p-8">
        {/* Dropzone */}
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            if (e.dataTransfer.files) addFiles(e.dataTransfer.files);
          }}
          onClick={() => inputRef.current?.click()}
          className={cn(
            "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed bg-card/40 p-10 text-center transition-colors",
            dragOver
              ? "border-primary bg-primary/5"
              : "border-border hover:border-primary/50",
          )}
        >
          <Upload className="h-10 w-10 text-muted-foreground" />
          <div className="text-base font-medium">
            把 .md / .markdown / .zip 拖到这里，或点击选择
          </div>
          <div className="text-sm text-muted-foreground">
            UTF-8 编码；.zip 内允许嵌套子目录的图片 / 附件，会自动提取并把 md 里的相对路径改写为可访问的 URL。
            <br />
            一期不接 docx / pdf；外链 (http/https) 与 data: 协议的图片保持原样。
          </div>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            multiple
            className="hidden"
            onChange={(e) => {
              if (e.target.files) addFiles(e.target.files);
              e.target.value = "";
            }}
          />
        </div>

        {/* Pending files */}
        {files.length > 0 && (
          <Card>
            <CardContent className="p-4">
              <div className="mb-3 flex items-center justify-between">
                <div className="text-sm font-medium">
                  待上传 {files.length} 个文件
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setFiles([])}
                  disabled={upload.isPending}
                >
                  全部移除
                </Button>
              </div>
              <ul className="divide-y">
                {files.map((f, i) => {
                  const isZip = /\.zip$/i.test(f.name);
                  return (
                  <li
                    key={`${f.name}-${i}`}
                    className="flex items-center justify-between gap-3 py-2 text-sm"
                  >
                    <div className="flex min-w-0 items-center gap-2">
                      {isZip ? (
                        <Archive className="h-4 w-4 shrink-0 text-amber-500" />
                      ) : (
                        <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                      )}
                      <span className="truncate">{f.name}</span>
                      <span className="text-xs text-muted-foreground shrink-0">
                        {formatBytes(f.size)}
                      </span>
                    </div>
                    <button
                      type="button"
                      className="text-xs text-muted-foreground hover:text-destructive"
                      onClick={() =>
                        setFiles((prev) => prev.filter((_, j) => j !== i))
                      }
                      disabled={upload.isPending}
                    >
                      移除
                    </button>
                  </li>
                  );
                })}
              </ul>
              <div className="mt-4 flex justify-end gap-2">
                <Button
                  onClick={() => upload.mutate(files)}
                  disabled={upload.isPending || files.length === 0}
                >
                  {upload.isPending ? "上传中..." : `开始解析 ${files.length} 个`}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Result */}
        {result && (
          <Card>
            <CardContent className="p-4">
              <div className="mb-3 text-sm font-medium">
                上传结果:成功 {result.created} · 失败 {result.failed}
              </div>
              <ul className="divide-y">
                {result.results.map((r, i) => (
                  <li
                    key={`${r.filename}-${i}`}
                    className="flex flex-col gap-1 py-2 text-sm md:flex-row md:items-center md:justify-between md:gap-3"
                  >
                    <div className="flex min-w-0 items-center gap-2">
                      {r.success ? (
                        <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />
                      ) : (
                        <XCircle className="h-4 w-4 shrink-0 text-destructive" />
                      )}
                      <span className="truncate">
                        {r.filename}
                        {r.success && r.title && r.title !== r.filename && (
                          <span className="text-muted-foreground"> → {r.title}</span>
                        )}
                      </span>
                      {r.success && r.error && (
                        <span className="ml-2 flex items-center gap-1 truncate text-xs text-amber-600 dark:text-amber-400">
                          <AlertTriangle className="h-3 w-3" />
                          {r.error}
                        </span>
                      )}
                    </div>
                    {r.success && r.wiki_id ? (
                      <Button
                        variant="link"
                        size="sm"
                        onClick={() => navigate(`/wiki/${r.wiki_id}`)}
                      >
                        查看
                      </Button>
                    ) : (
                      !r.success && (
                        <span className="text-xs text-destructive">
                          {r.error ?? "未知错误"}
                        </span>
                      )
                    )}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}
      </div>
    </>
  );
}
