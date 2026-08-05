/**
 * Minimal toast — single instance, controlled by a tiny global store. We avoid
 * the full radix-toast surface for the MVP because we only need success/error
 * notifications.
 */
import { useSyncExternalStore } from "react";
import { CheckCircle2, AlertCircle, X } from "lucide-react";
import { cn } from "@/lib/utils";

export type ToastKind = "success" | "error" | "info";
export interface ToastMsg {
  id: number;
  kind: ToastKind;
  text: string;
}

let counter = 0;
let queue: ToastMsg[] = [];
const listeners = new Set<() => void>();

function emit() {
  for (const l of listeners) l();
}

export const toast = {
  show(text: string, kind: ToastKind = "info", durationMs = 3500) {
    const id = ++counter;
    queue = [...queue, { id, kind, text }];
    emit();
    setTimeout(() => {
      queue = queue.filter((t) => t.id !== id);
      emit();
    }, durationMs);
  },
  success(text: string) { this.show(text, "success"); },
  error(text: string) { this.show(text, "error", 5000); },
  info(text: string) { this.show(text, "info"); },
  dismiss(id: number) {
    queue = queue.filter((t) => t.id !== id);
    emit();
  },
};

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export function ToastViewport() {
  const items = useSyncExternalStore(subscribe, () => queue, () => queue);
  return (
    <div className="pointer-events-none fixed inset-x-0 top-3 z-[100] flex flex-col items-center gap-2 px-4">
      {items.map((t) => (
        <div
          key={t.id}
          className={cn(
            "pointer-events-auto flex w-full max-w-sm items-center gap-3 rounded-lg border bg-card px-4 py-2.5 text-sm shadow-lg",
            t.kind === "success" && "border-emerald-500/40",
            t.kind === "error" && "border-destructive/50",
          )}
        >
          {t.kind === "success" && (
            <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
          )}
          {t.kind === "error" && (
            <AlertCircle className="h-4 w-4 text-destructive shrink-0" />
          )}
          <span className="flex-1 leading-snug">{t.text}</span>
          <button
            type="button"
            onClick={() => toast.dismiss(t.id)}
            className="text-muted-foreground hover:text-foreground"
            aria-label="关闭通知"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
}
