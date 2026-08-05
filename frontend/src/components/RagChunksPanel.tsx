import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ChevronDown, ChevronUp, Search } from "lucide-react";

import { ragApi } from "@/api/rag";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
export function RagChunksPanel() {
  const [open, setOpen] = useState(false);
  const [wikiId, setWikiId] = useState("");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const limit = 20;

  const wikiIdNum = wikiId.trim() ? Number(wikiId) : undefined;
  const enabled = open && (wikiIdNum === undefined || !Number.isNaN(wikiIdNum));

  const chunksQ = useQuery({
    queryKey: ["rag-chunks", wikiIdNum, q, offset],
    queryFn: () =>
      ragApi.listChunks({
        wiki_id: wikiIdNum,
        q: q.trim() || undefined,
        limit,
        offset,
      }),
    enabled,
  });

  const items = chunksQ.data?.items ?? [];
  const total = chunksQ.data?.total ?? 0;

  return (
    <div className="space-y-3 rounded-lg border border-dashed border-border p-3">
      <button
        type="button"
        className="flex w-full items-center justify-between text-left text-sm font-medium"
        onClick={() => setOpen((o) => !o)}
      >
        <span>查看本地 RAG 片段（chunk）</span>
        {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
      </button>
      {open && (
        <>
          <p className="text-xs text-muted-foreground">
            数据保存在 SQLite 表 <code className="rounded bg-muted px-1">rag_chunks</code>
            ；也可调用{" "}
            <code className="rounded bg-muted px-1">GET /api/rag/chunks</code>（需{" "}
            <code className="rounded bg-muted px-1">X-SL-Token</code>）。
          </p>
          <div className="flex flex-wrap gap-2">
            <Input
              placeholder="Wiki ID（可选）"
              value={wikiId}
              onChange={(e) => {
                setWikiId(e.target.value);
                setOffset(0);
              }}
              className="h-8 w-28"
            />
            <div className="relative min-w-[12rem] flex-1">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="搜索片段正文…"
                value={q}
                onChange={(e) => {
                  setQ(e.target.value);
                  setOffset(0);
                }}
                className="h-8 pl-8"
              />
            </div>
          </div>
          {chunksQ.isLoading && (
            <p className="text-xs text-muted-foreground">加载中…</p>
          )}
          {chunksQ.isError && (
            <p className="text-xs text-destructive">{(chunksQ.error as Error).message}</p>
          )}
          {!chunksQ.isLoading && items.length === 0 && (
            <p className="text-xs text-muted-foreground">
              暂无片段。请先在上方「重建全部 Wiki 向量索引」。
            </p>
          )}
          <ul className="max-h-80 space-y-2 overflow-y-auto text-xs">
            {items.map((c) => (
              <li
                key={c.id}
                className="rounded-md border bg-muted/30 px-3 py-2"
              >
                <div className="mb-1 flex flex-wrap items-center gap-x-2 gap-y-0.5">
                  <Link
                    to={`/wiki/${c.wiki_id}`}
                    className="font-medium text-primary hover:underline"
                  >
                    {c.wiki_title}
                  </Link>
                  <span className="text-muted-foreground">
                    #{c.chunk_index} · {c.text_length} 字
                  </span>
                  {c.heading && (
                    <span className="text-muted-foreground">· {c.heading}</span>
                  )}
                </div>
                <pre className="whitespace-pre-wrap break-words font-sans text-[11px] leading-relaxed text-foreground/90">
                  {c.text}
                </pre>
              </li>
            ))}
          </ul>
          {total > limit && (
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs text-muted-foreground">
                共 {total} 条，显示 {offset + 1}–{Math.min(offset + limit, total)}
              </span>
              <div className="flex gap-1">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={offset === 0}
                  onClick={() => setOffset((o) => Math.max(0, o - limit))}
                >
                  上一页
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={offset + limit >= total}
                  onClick={() => setOffset((o) => o + limit)}
                >
                  下一页
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
