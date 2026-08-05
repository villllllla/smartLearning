import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ExternalLink,
  Flame,
  Loader2,
  Newspaper,
  RefreshCw,
  Sparkles,
} from "lucide-react";

import { aiNewsApi, type AiNewsDigest, type AiNewsItem } from "@/api/aiNews";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "@/components/ui/toast";

const NEWS_KEY = ["ai-news"];

function fmtTime(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function NewsRow({ item }: { item: AiNewsItem }) {
  return (
    <div className="flex gap-3 rounded-md border bg-background/60 p-3">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold text-primary">
        {item.rank}
      </div>
      <div className="min-w-0 flex-1 space-y-1">
        <a
          href={item.url}
          target="_blank"
          rel="noreferrer"
          className="group flex items-start gap-1.5 font-medium leading-snug hover:text-primary"
        >
          <span className="min-w-0">{item.title}</span>
          <ExternalLink className="mt-1 h-3.5 w-3.5 shrink-0 opacity-50 group-hover:opacity-100" />
        </a>
        {item.summary ? (
          <p className="text-sm text-muted-foreground">{item.summary}</p>
        ) : null}
        {item.why ? (
          <p className="text-xs text-muted-foreground">💡 {item.why}</p>
        ) : null}
        <div className="flex flex-wrap items-center gap-2 pt-0.5 text-xs text-muted-foreground">
          <Badge variant="outline">{item.source}</Badge>
          <span className="inline-flex items-center gap-1 text-orange-500">
            <Flame className="h-3 w-3" />
            {item.heat_score}
          </span>
          {item.published_at ? (
            <span>{fmtTime(item.published_at)}</span>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function DigestCard({ digest }: { digest: AiNewsDigest }) {
  return (
    <Card>
      <CardContent className="space-y-3 p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Newspaper className="h-4 w-4" />
            {fmtTime(digest.created_at)}
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Badge variant="secondary">
              {digest.used_llm ? (
                <>
                  <Sparkles className="mr-1 h-3 w-3" />
                  模型精选
                </>
              ) : (
                "热度排序"
              )}
            </Badge>
            <span>
              {digest.item_count} 条 / {digest.total_candidates} 候选
            </span>
          </div>
        </div>
        <div className="space-y-2">
          {digest.items.map((it) => (
            <NewsRow key={it.id} item={it} />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

export function AiNewsPage() {
  const qc = useQueryClient();
  const listQ = useQuery({
    queryKey: NEWS_KEY,
    queryFn: () => aiNewsApi.list({ limit: 30 }),
  });

  const trigger = useMutation({
    mutationFn: () => aiNewsApi.trigger(),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: NEWS_KEY });
      toast.success(res.message);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const digests = listQ.data?.items ?? [];

  return (
    <>
      <PageHeader
        title="AI 资讯"
        description="多源抓取 · 模型精选 · 每日飞书推送热点 Top N（含出处与链接）"
        actions={
          <Button onClick={() => trigger.mutate()} disabled={trigger.isPending}>
            {trigger.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="mr-2 h-4 w-4" />
            )}
            立即抓取
          </Button>
        }
      />

      <div className="mx-auto max-w-4xl space-y-4 p-4 md:p-8">
        {listQ.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            加载中…
          </div>
        ) : digests.length === 0 ? (
          <Card>
            <CardContent className="p-8 text-center text-sm text-muted-foreground">
              还没有资讯。点右上角「立即抓取」拉取一批，或在设置里开启每日定时推送。
            </CardContent>
          </Card>
        ) : (
          digests.map((d) => <DigestCard key={d.id} digest={d} />)
        )}
      </div>
    </>
  );
}
