/** HH:MM push time parsing — must match backend ``push_schedule_service._TIME_RE``. */
const TIME_RE = /^([01]?\d|2[0-3]):([0-5]\d)$/;

export function parsePushTimesInput(text: string): { ok: true; times: string[] } | { ok: false; error: string } {
  const parts = text
    .split(/[,，\s]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  if (parts.length === 0) {
    return { ok: false, error: "至少填写一个推送时间，格式 HH:MM（如 09:00）" };
  }
  const bad: string[] = [];
  const times: string[] = [];
  for (const p of parts) {
    const m = TIME_RE.exec(p);
    if (!m) {
      bad.push(p);
      continue;
    }
    times.push(`${Number(m[1]).toString().padStart(2, "0")}:${m[2]}`);
  }
  if (bad.length > 0) {
    return {
      ok: false,
      error: `时间格式无效: ${bad.join("、")}，请使用 HH:MM（如 09:00、18:30）`,
    };
  }
  return { ok: true, times: [...new Set(times)].sort() };
}
