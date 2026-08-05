/**

 * Tiny `fetch` wrapper. We avoid axios to keep the bundle slim and to make

 * server errors flow through a single typed code path.

 */

import { clearAuth, getStoredToken } from "@/lib/auth";



const BASE = "/api";



/** Must match backend `SL_BOT_API_TOKEN` when tunnel hardening is enabled. */

const SL_BOT_TOKEN = (import.meta.env.VITE_SL_BOT_TOKEN as string | undefined)?.trim() ?? "";



export type ApiRequestOptions = RequestInit & {

  /** Do not attach JWT / bot token (login, register). */

  skipAuth?: boolean;

};



/** Attach Bearer JWT and optional `X-SL-Token` for `/api/*`. */

export function withAuthHeaders(init?: ApiRequestOptions): RequestInit {

  const { skipAuth, ...rest } = init ?? {};

  const headers = new Headers(rest.headers);



  if (!skipAuth) {

    const token = getStoredToken();

    if (token) {

      headers.set("Authorization", `Bearer ${token}`);

    } else if (SL_BOT_TOKEN) {

      headers.set("X-SL-Token", SL_BOT_TOKEN);

    }

  }



  return { ...rest, headers };

}



export class ApiError extends Error {

  constructor(public status: number, message: string, public payload?: unknown) {

    super(message);

  }

}



/** Turn FastAPI `detail` (string | validation object | array) into readable text. */

export function formatApiDetail(detail: unknown): string {

  if (detail == null) return "";

  if (typeof detail === "string") return detail;

  if (Array.isArray(detail)) {

    const parts = detail.map((item) => formatApiDetail(item)).filter(Boolean);

    return parts.length > 0 ? parts.join("; ") : "请求参数无效";

  }

  if (typeof detail === "object") {

    const o = detail as Record<string, unknown>;

    if (typeof o.msg === "string") {

      const loc = Array.isArray(o.loc)

        ? o.loc.filter((x) => x !== "body").join(".")

        : "";

      return loc ? `${loc}: ${o.msg}` : o.msg;

    }

    if (typeof o.message === "string") return o.message;

    try {

      return JSON.stringify(detail);

    } catch {

      return "请求失败";

    }

  }

  return String(detail);

}



async function handle<T>(resp: Response): Promise<T> {

  if (resp.status === 204) return undefined as T;

  const ct = resp.headers.get("content-type") ?? "";

  const body = ct.includes("application/json") ? await resp.json() : await resp.text();

  if (!resp.ok) {

    const detail =

      typeof body === "object" && body !== null && "detail" in body

        ? formatApiDetail((body as { detail: unknown }).detail)

        : typeof body === "string"

          ? body

          : `HTTP ${resp.status}`;

    const sessionExpiredDetails = new Set([

      "请先登录",

      "登录已过期，请重新登录",

      "无效的登录凭证",

      "未登录或登录已过期",

      "用户不存在或无权访问",

    ]);

    if (resp.status === 401 && getStoredToken() && sessionExpiredDetails.has(detail)) {

      clearAuth();

      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {

        window.location.href = `/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`;

      }

    }

    throw new ApiError(resp.status, detail, body);

  }

  return body as T;

}



function request<T>(path: string, init?: ApiRequestOptions): Promise<T> {

  return fetch(`${BASE}${path}`, withAuthHeaders(init)).then(handle<T>);

}



export const api = {

  get: <T>(path: string, options?: ApiRequestOptions) => request<T>(path, options),

  post: <T>(path: string, body?: unknown, options?: ApiRequestOptions) =>

    request<T>(path, {

      ...options,

      method: "POST",

      headers: { "Content-Type": "application/json", ...(options?.headers as Record<string, string>) },

      body: body === undefined ? undefined : JSON.stringify(body),

    }),

  patch: <T>(path: string, body?: unknown, options?: ApiRequestOptions) =>

    request<T>(path, {

      ...options,

      method: "PATCH",

      headers: { "Content-Type": "application/json", ...(options?.headers as Record<string, string>) },

      body: body === undefined ? undefined : JSON.stringify(body),

    }),

  put: <T>(path: string, body?: unknown, options?: ApiRequestOptions) =>

    request<T>(path, {

      ...options,

      method: "PUT",

      headers: { "Content-Type": "application/json", ...(options?.headers as Record<string, string>) },

      body: body === undefined ? undefined : JSON.stringify(body),

    }),

  delete: <T>(path: string, options?: ApiRequestOptions) =>

    request<T>(path, { ...options, method: "DELETE" }),

  upload: <T>(path: string, formData: FormData, options?: ApiRequestOptions) =>

    request<T>(path, { ...options, method: "POST", body: formData }),



  /** Trigger a binary file download (CSV/JSON/zip). Filename is parsed from

   * Content-Disposition when present, falling back to `defaultName`. */

  async download(path: string, defaultName: string): Promise<void> {

    const resp = await fetch(`${BASE}${path}`, withAuthHeaders());

    if (!resp.ok) throw new ApiError(resp.status, `下载失败 (${resp.status})`);

    const cd = resp.headers.get("Content-Disposition") ?? "";

    const m = /filename\*?=(?:UTF-8'')?["']?([^;"']+)/i.exec(cd);

    const filename = m ? decodeURIComponent(m[1]) : defaultName;

    const blob = await resp.blob();

    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");

    a.href = url;

    a.download = filename;

    document.body.appendChild(a);

    a.click();

    a.remove();

    URL.revokeObjectURL(url);

  },

};


