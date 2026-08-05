import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpen,
  ChevronLeft,
  ChevronRight,
  ImagePlus,
  Loader2,
  Plus,
  Send,
  Trash2,
  X,
  MessageSquareText,
  Square,
} from "lucide-react";

import {
  type AttachmentRef,
  type ChatDetail,
  type ChatSummary,
  type MessageSummary,
  type RagSource,
  chatApi,
  streamChat,
} from "@/api/chat";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Empty } from "@/components/Empty";
import { MarkdownView } from "@/components/MarkdownView";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/components/ui/toast";
import { cn, formatDateTime } from "@/lib/utils";

interface PendingAttachment extends AttachmentRef {
  url: string;
  name: string;
}

export function ChatPage() {
  const qc = useQueryClient();
  const [activeId, setActiveId] = useState<number | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  /** Avoid racing delete + stale chat list: only auto-select first chat on first load. */
  const needsInitialChatPick = useRef(true);

  const chats = useQuery({
    queryKey: ["chats"],
    queryFn: () => chatApi.list(),
  });

  // First visit only: pick the first session once the list has loaded.
  useEffect(() => {
    if (activeId != null) {
      needsInitialChatPick.current = false;
      return;
    }
    if (!needsInitialChatPick.current) return;
    if (!chats.isSuccess) return;
    if (!chats.data?.length) {
      needsInitialChatPick.current = false;
      return;
    }
    setActiveId(chats.data[0].id);
    needsInitialChatPick.current = false;
  }, [activeId, chats.isSuccess, chats.data]);

  const create = useMutation({
    mutationFn: () => chatApi.create({}),
    onSuccess: (chat) => {
      setActiveId(chat.id);
      qc.invalidateQueries({ queryKey: ["chats"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const remove = useMutation({
    mutationFn: (id: number) => chatApi.remove(id),
    onSuccess: async (_, deletedId) => {
      qc.removeQueries({ queryKey: ["chat", deletedId] });
      await qc.refetchQueries({ queryKey: ["chats"] });
      const next = qc.getQueryData<ChatSummary[]>(["chats"]) ?? [];
      setActiveId((curr) => {
        if (curr !== deletedId) return curr;
        return next[0]?.id ?? null;
      });
      toast.info("已删除会话");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const chatList = chats.data ?? [];

  return (
    <div className="flex h-[calc(100dvh-5rem)] overflow-hidden md:h-[calc(100dvh)]">
      {/* 会话列表：贴左、可折叠 */}
      <aside
        className={cn(
          "flex shrink-0 flex-col border-r bg-card/50 transition-[width] duration-200 ease-out",
          sidebarOpen ? "w-56" : "w-11",
        )}
      >
        <button
          type="button"
          onClick={() => setSidebarOpen((o) => !o)}
          className="flex w-full items-center gap-2 border-b px-2 py-3 text-left text-sm font-semibold hover:bg-accent/60"
          aria-expanded={sidebarOpen}
          title={sidebarOpen ? "收起会话列表" : "展开会话列表"}
        >
          {sidebarOpen ? (
            <ChevronLeft className="h-4 w-4 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
          )}
          {sidebarOpen && <span>会话</span>}
          {!sidebarOpen && <span className="sr-only">会话</span>}
        </button>

        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          {sidebarOpen ? (
            <>
              <div className="shrink-0 p-2">
                <Button
                  className="w-full"
                  size="sm"
                  onClick={() => create.mutate()}
                  disabled={create.isPending}
                >
                  <Plus className="h-4 w-4" />
                  新建会话
                </Button>
              </div>
              <div className="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-1.5 pb-2">
                {chatList.length === 0 && (
                  <div className="px-2 py-4 text-xs text-muted-foreground">尚无会话</div>
                )}
                {chatList.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => setActiveId(c.id)}
                    className={cn(
                      "group flex w-full items-center justify-between gap-2 rounded-md px-2 py-2 text-left text-sm transition-colors",
                      activeId === c.id
                        ? "bg-primary/10 text-foreground"
                        : "text-muted-foreground hover:bg-accent hover:text-foreground",
                    )}
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <MessageSquareText className="h-3.5 w-3.5 shrink-0" />
                      <span className="truncate">{c.title}</span>
                    </span>
                    <Trash2
                      className="h-3.5 w-3.5 shrink-0 opacity-0 transition-opacity group-hover:opacity-60 hover:!opacity-100 hover:text-destructive"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (confirm(`删除会话「${c.title}」?`)) remove.mutate(c.id);
                      }}
                    />
                  </button>
                ))}
              </div>
            </>
          ) : (
            <div className="flex flex-1 flex-col items-center gap-1 overflow-y-auto py-2">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                title="新建会话"
                onClick={() => create.mutate()}
                disabled={create.isPending}
              >
                <Plus className="h-4 w-4" />
              </Button>
              {chatList.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  title={c.title}
                  onClick={() => setActiveId(c.id)}
                  className={cn(
                    "flex h-8 w-8 items-center justify-center rounded-md transition-colors",
                    activeId === c.id
                      ? "bg-primary/15 text-primary"
                      : "text-muted-foreground hover:bg-accent",
                  )}
                >
                  <MessageSquareText className="h-4 w-4" />
                </button>
              ))}
            </div>
          )}
        </div>
      </aside>

      {/* 对话主区域：占满剩余宽度 */}
      <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-background">
        {activeId == null ? (
          <div className="flex h-full items-center justify-center p-8">
            <Empty
              title="选择一个会话开始,或新建一个"
              description="左侧可展开「会话」列表；新建会话后即可开始对话。"
              action={
                <Button onClick={() => create.mutate()}>
                  <Plus className="h-4 w-4" />
                  新建会话
                </Button>
              }
            />
          </div>
        ) : (
          <ActiveChat key={activeId} chatId={activeId} />
        )}
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Active chat panel
// ---------------------------------------------------------------------------

interface ActiveChatProps {
  chatId: number;
}

function ActiveChat({ chatId }: ActiveChatProps) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ["chat", chatId],
    queryFn: () => chatApi.get(chatId),
  });

  const [input, setInput] = useState("");
  const [useRag, setUseRag] = useState(true);
  const [pending, setPending] = useState<PendingAttachment[]>([]);
  const [streaming, setStreaming] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const stickToBottomRef = useRef(true);

  const allMessages: MessageSummary[] = useMemo(() => {
    const base = data?.messages ?? [];
    if (streaming != null) {
      return [
        ...base,
        {
          id: -1,
          chat_id: chatId,
          role: "assistant",
          content_text: streaming,
          attachments_json: [],
          token_usage_json: null,
          created_at: new Date().toISOString(),
        } satisfies MessageSummary,
      ];
    }
    return base;
  }, [data?.messages, streaming, chatId]);

  const scrollToBottom = (smooth: boolean) => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTo({
        top: el.scrollHeight,
        behavior: smooth ? "smooth" : "instant",
      });
    }
    bottomRef.current?.scrollIntoView({
      block: "end",
      behavior: smooth ? "smooth" : "instant",
    });
  };

  useEffect(() => {
    stickToBottomRef.current = true;
  }, [chatId]);

  // After messages paint (incl. Markdown), jump to bottom when opening a chat.
  useLayoutEffect(() => {
    if (isLoading || !data) return;
    if (!stickToBottomRef.current) return;
    scrollToBottom(false);
    const t1 = window.setTimeout(() => scrollToBottom(false), 0);
    const t2 = window.setTimeout(() => scrollToBottom(false), 120);
    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
  }, [chatId, isLoading, data, allMessages.length]);

  useEffect(() => {
    const root = scrollRef.current;
    if (!root) return;
    const onScroll = () => {
      const dist = root.scrollHeight - root.scrollTop - root.clientHeight;
      stickToBottomRef.current = dist < 96;
    };
    root.addEventListener("scroll", onScroll, { passive: true });
    return () => root.removeEventListener("scroll", onScroll);
  }, [chatId]);

  useEffect(() => {
    const root = scrollRef.current;
    if (!root) return;
    const ro = new ResizeObserver(() => {
      if (!stickToBottomRef.current) return;
      scrollToBottom(streaming != null);
    });
    ro.observe(root);
    return () => ro.disconnect();
  }, [chatId, streaming]);

  useEffect(() => {
    if (streaming == null) return;
    scrollToBottom(true);
  }, [streaming]);

  const upload = useMutation({
    mutationFn: (file: File) => chatApi.upload(file),
    onSuccess: (res, file) => {
      setPending((p) => [
        ...p,
        { id: res.id, mime: res.mime, url: res.url, name: file.name },
      ]);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const handleFiles = (files: FileList | null) => {
    if (!files) return;
    for (const f of Array.from(files)) upload.mutate(f);
  };

  const send = async () => {
    const text = input.trim();
    if (!text || streaming != null) return;

    setInput("");
    const attachments = pending.map((p) => ({ id: p.id, mime: p.mime }));
    setPending([]);

    // Optimistic user message
    const optimistic: MessageSummary = {
      id: -Date.now(),
      chat_id: chatId,
      role: "user",
      content_text: text,
      attachments_json: attachments,
      token_usage_json: null,
      created_at: new Date().toISOString(),
    };
    qc.setQueryData<ChatDetail | undefined>(["chat", chatId], (prev) =>
      prev ? { ...prev, messages: [...prev.messages, optimistic] } : prev,
    );
    stickToBottomRef.current = true;
    setStreaming("");

    abortRef.current = new AbortController();
    try {
      await streamChat(
        chatId,
        { content: text, attachments, use_rag: useRag },
        {
          onDelta: (chunk) => setStreaming((s) => (s ?? "") + chunk),
          onDone: (done) => {
            setStreaming(null);
            qc.invalidateQueries({ queryKey: ["chat", chatId] });
            qc.invalidateQueries({ queryKey: ["chats"] });
            if (done.interrupted) {
              toast.info("已停止生成，部分内容已保存");
            }
          },
          onError: (msg) => {
            setStreaming(null);
            toast.error(msg);
            qc.invalidateQueries({ queryKey: ["chat", chatId] });
          },
          signal: abortRef.current.signal,
        },
      );
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        toast.error((e as Error).message);
      }
      setStreaming(null);
      qc.invalidateQueries({ queryKey: ["chat", chatId] });
    } finally {
      abortRef.current = null;
    }
  };

  const saveChatToWiki = useMutation({
    mutationFn: () => chatApi.saveToWiki(chatId),
    onSuccess: (res) => {
      toast.success(`已保存到知识库：${res.title}`);
      qc.invalidateQueries({ queryKey: ["wiki-list"] });
      navigate(res.url_path);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const saveMessageToWiki = useMutation({
    mutationFn: (messageId: number) => chatApi.saveMessageToWiki(chatId, messageId),
    onSuccess: (res) => {
      toast.success(`已保存到知识库：${res.title}`);
      qc.invalidateQueries({ queryKey: ["wiki-list"] });
      navigate(res.url_path);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const stop = () => {
    abortRef.current?.abort();
    setStreaming(null);
    // Server persists partial reply in stream finally; refetch after abort.
    setTimeout(() => {
      qc.invalidateQueries({ queryKey: ["chat", chatId] });
      qc.invalidateQueries({ queryKey: ["chats"] });
    }, 400);
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Title bar */}
      <div className="flex shrink-0 items-center justify-between gap-2 border-b px-4 py-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold">
            {data?.title ?? (isLoading ? "加载中..." : "会话")}
          </div>
          {data && (
            <div className="text-xs text-muted-foreground">
              {data.messages.length} 条消息 · 创建于 {formatDateTime(data.created_at)}
            </div>
          )}
        </div>
        <Button
          variant="outline"
          size="sm"
          className="shrink-0 gap-1.5"
          disabled={
            isLoading ||
            !data?.messages.some((m) => m.role === "user" || m.role === "assistant") ||
            saveChatToWiki.isPending
          }
          onClick={() => saveChatToWiki.mutate()}
          title="将整段用户/助手对话导出为新的 Wiki 条目"
        >
          {saveChatToWiki.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <BookOpen className="h-3.5 w-3.5" />
          )}
          保存到知识库
        </Button>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-4 py-3 md:px-6 md:py-4">
        {allMessages.length === 0 && (
          <div className="mt-8 text-center text-sm text-muted-foreground">
            发送第一条消息开始对话。系统会附上当前 chat_general Prompt 作为 system message。
          </div>
        )}
        <div className="space-y-4">
          {allMessages.map((m) => (
            <MessageBubble
              key={`${m.id}-${m.created_at}`}
              msg={m}
              onSaveToWiki={
                m.id > 0 && (m.role === "assistant" || m.role === "user")
                  ? () => saveMessageToWiki.mutate(m.id)
                  : undefined
              }
              savingToWiki={saveMessageToWiki.isPending}
            />
          ))}
          {streaming != null && streaming === "" && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-primary" />
              模型生成中...
            </div>
          )}
          <div ref={bottomRef} className="h-px shrink-0" aria-hidden />
        </div>
      </div>

      {/* Composer */}
      <div className="shrink-0 border-t px-4 py-3 md:px-6 md:py-4">
        {pending.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-2">
            {pending.map((a, i) => (
              <div
                key={a.id}
                className="group relative inline-flex items-center gap-2 rounded-md border bg-muted/40 p-1.5 text-xs"
              >
                <img
                  src={a.url}
                  alt={a.name}
                  className="h-10 w-10 rounded object-cover"
                />
                <span className="max-w-[120px] truncate">{a.name}</span>
                <button
                  type="button"
                  className="text-muted-foreground hover:text-destructive"
                  onClick={() =>
                    setPending((p) => p.filter((_, j) => j !== i))
                  }
                  aria-label="移除附件"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
        <label className="mb-2 flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
          <input
            type="checkbox"
            checked={useRag}
            onChange={(e) => setUseRag(e.target.checked)}
            className="rounded border-input"
            disabled={streaming != null}
          />
          使用 Wiki 知识库 (RAG，bge-small-zh 检索后注入上下文)
        </label>
        <div className="flex items-end gap-2">
          <Button
            variant="outline"
            size="icon"
            aria-label="添加图片"
            onClick={() => fileRef.current?.click()}
            disabled={streaming != null || upload.isPending}
            title="添加图片(需模型 supports_vision=true)"
          >
            <ImagePlus className="h-4 w-4" />
          </Button>
          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg,image/gif,image/webp"
            multiple
            className="hidden"
            onChange={(e) => {
              handleFiles(e.target.files);
              e.target.value = "";
            }}
          />
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="输入消息,Shift+Enter 换行,Enter 发送"
            rows={3}
            className="min-h-[4.5rem] resize-none"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            disabled={streaming != null}
          />
          {streaming != null ? (
            <Button variant="destructive" onClick={stop} aria-label="停止">
              <Square className="h-4 w-4" />
              停止
            </Button>
          ) : (
            <Button onClick={send} disabled={!input.trim()} aria-label="发送">
              <Send className="h-4 w-4" />
              发送
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Message bubble
// ---------------------------------------------------------------------------

function MessageBubble({
  msg,
  onSaveToWiki,
  savingToWiki,
}: {
  msg: MessageSummary;
  onSaveToWiki?: () => void;
  savingToWiki?: boolean;
}) {
  const isUser = msg.role === "user";
  const canSave = onSaveToWiki && (msg.content_text || "").trim().length > 0;
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[80%] rounded-lg px-4 py-3 text-sm",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-foreground",
        )}
      >
        <div
          className={cn(
            "mb-1 flex flex-wrap items-center gap-2 text-[11px]",
            isUser ? "opacity-80" : "opacity-70",
          )}
        >
          <Badge
            variant={isUser ? "secondary" : "outline"}
            className="h-4 rounded-sm px-1.5 py-0 text-[10px]"
          >
            {msg.role}
          </Badge>
          <span>{formatDateTime(msg.created_at)}</span>
          {canSave && (
            <button
              type="button"
              className={cn(
                "ml-auto inline-flex items-center gap-1 rounded px-1.5 py-0.5 transition-colors",
                isUser
                  ? "hover:bg-primary-foreground/20"
                  : "hover:bg-background/60",
              )}
              disabled={savingToWiki}
              onClick={onSaveToWiki}
              title="另存为 Wiki 知识条目"
            >
              {savingToWiki ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <BookOpen className="h-3 w-3" />
              )}
              <span>保存到知识库</span>
            </button>
          )}
        </div>
        {msg.attachments_json && msg.attachments_json.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-2">
            {msg.attachments_json.map((a) => (
              <img
                key={a.id}
                src={`/api/attachments/${a.id}`}
                alt=""
                className="h-24 w-24 rounded border object-cover"
              />
            ))}
          </div>
        )}
        {isUser ? (
          <div className="whitespace-pre-wrap leading-relaxed">{msg.content_text}</div>
        ) : (
          <MarkdownView source={msg.content_text || ""} />
        )}
        <RagSourcesFooter msg={msg} />
      </div>
    </div>
  );
}

function RagSourcesFooter({ msg }: { msg: MessageSummary }) {
  if (msg.role !== "assistant" || !msg.token_usage_json) return null;
  const raw = msg.token_usage_json.rag_sources;
  if (!Array.isArray(raw) || raw.length === 0) return null;
  const sources = raw as RagSource[];
  return (
    <div className="mt-3 border-t border-border/60 pt-2">
      <p className="mb-1.5 text-[11px] font-medium text-muted-foreground">参考文档</p>
      <ul className="space-y-1 text-xs">
        {sources.map((s, i) => (
          <li key={`${s.wiki_id}-${s.chunk_index}-${i}`}>
            <Link
              to={s.url_path}
              className="text-primary underline-offset-2 hover:underline"
            >
              {s.wiki_title}
              {s.heading ? ` · ${s.heading}` : ""}
            </Link>
            <span className="ml-1 text-muted-foreground">({(s.score * 100).toFixed(0)}%)</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
