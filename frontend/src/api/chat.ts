import { api, withAuthHeaders } from "./client";

export interface AttachmentRef {
  id: string;
  mime: string;
}

export interface MessageSummary {
  id: number;
  chat_id: number;
  role: "system" | "user" | "assistant";
  content_text: string;
  attachments_json: AttachmentRef[];
  token_usage_json: Record<string, unknown> | null;
  created_at: string;
}

export interface ChatSummary {
  id: number;
  title: string;
  model_id: number | null;
  prompt_template_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface ChatDetail extends ChatSummary {
  messages: MessageSummary[];
}

export interface RagSource {
  wiki_id: number;
  wiki_title: string;
  heading: string | null;
  chunk_index: number;
  score: number;
  url_path: string;
  excerpt: string;
}

export interface SendMessageRequest {
  content: string;
  attachments?: AttachmentRef[];
  model_id?: number | null;
  /** 检索 Wiki 知识库（bge-small-zh RAG） */
  use_rag?: boolean | null;
}

export interface SendMessageResponse {
  user_message: MessageSummary;
  assistant_message: MessageSummary;
}

export interface UploadResponse {
  id: string;
  mime: string;
  url: string;
  size: number;
}

export interface SaveToWikiResponse {
  wiki_id: number;
  title: string;
  url_path: string;
}

export const chatApi = {
  list: () => api.get<ChatSummary[]>("/chats"),
  create: (
    body: { title?: string; model_id?: number | null; prompt_template_id?: number | null } = {},
  ) => api.post<ChatDetail>("/chats", body),
  get: (id: number) => api.get<ChatDetail>(`/chats/${id}`),
  update: (
    id: number,
    body: { title?: string; model_id?: number | null; prompt_template_id?: number | null },
  ) => api.patch<ChatSummary>(`/chats/${id}`, body),
  remove: (id: number) => api.delete<void>(`/chats/${id}`),
  send: (id: number, body: SendMessageRequest) =>
    api.post<SendMessageResponse>(`/chats/${id}/messages`, body),
  saveToWiki: (chatId: number, body: { title?: string } = {}) =>
    api.post<SaveToWikiResponse>(`/chats/${chatId}/save-to-wiki`, body),
  saveMessageToWiki: (
    chatId: number,
    messageId: number,
    body: { title?: string } = {},
  ) =>
    api.post<SaveToWikiResponse>(
      `/chats/${chatId}/messages/${messageId}/save-to-wiki`,
      body,
    ),
  upload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file, file.name);
    return api.upload<UploadResponse>("/attachments", fd);
  },
};

/** Open an SSE-like stream for the next assistant reply. Calls back with deltas
 *  and resolves when the server sends ``done``. The browser fetch does not
 *  natively parse SSE, so we read the body line-by-line ourselves.
 */
export interface StreamDonePayload {
  chat_id: number;
  user_message_id?: number | null;
  assistant_message_id?: number | null;
  assistant_saved?: boolean;
  interrupted?: boolean;
  rag_sources?: RagSource[];
}

export interface StreamHandlers {
  onDelta: (text: string) => void;
  onDone?: (payload: StreamDonePayload) => void;
  onError?: (msg: string) => void;
  signal?: AbortSignal;
}

export async function streamChat(
  chatId: number,
  body: SendMessageRequest,
  handlers: StreamHandlers,
): Promise<void> {
  const resp = await fetch(
    `/api/chats/${chatId}/stream`,
    withAuthHeaders({
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: handlers.signal,
    }),
  );
  if (!resp.ok || !resp.body) {
    handlers.onError?.(`HTTP ${resp.status}`);
    return;
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const evt = parseSseBlock(block);
      if (!evt) continue;
      if (evt.event === "delta") handlers.onDelta(evt.data.text ?? "");
      else if (evt.event === "done")
        handlers.onDone?.(evt.data as StreamDonePayload);
      else if (evt.event === "error") handlers.onError?.(evt.data.message ?? "unknown");
    }
  }
}

function parseSseBlock(block: string): { event: string; data: any } | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return { event, data: { raw: dataLines.join("\n") } };
  }
}
