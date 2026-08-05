/** Format UTC-naive remind_at stored by backend using the todo's IANA timezone. */
export function formatTodoRemindAt(iso: string, timezone: string): string {
  const s = iso.includes("T") ? iso : iso.replace(" ", "T");
  const d = new Date(s.endsWith("Z") ? s : `${s}Z`);
  return d.toLocaleString("zh-CN", {
    timeZone: timezone,
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

export function remindTimeFromUtcIso(iso: string, timezone: string): string {
  const s = iso.includes("T") ? iso : iso.replace(" ", "T");
  const d = new Date(s.endsWith("Z") ? s : `${s}Z`);
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: timezone,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(d);
  const hh = parts.find((p) => p.type === "hour")?.value ?? "21";
  const mm = parts.find((p) => p.type === "minute")?.value ?? "00";
  return `${hh}:${mm}`;
}

export function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function canEditTodo(item: {
  plan_date: string | null;
  status: string;
}): boolean {
  if (item.status === "cancelled") return false;
  if (item.status === "done" || item.status === "clarifying") return true;
  if (!item.plan_date) return false;
  if (!["scheduled", "reminded", "snoozed"].includes(item.status)) return false;
  return item.plan_date >= todayIso();
}
