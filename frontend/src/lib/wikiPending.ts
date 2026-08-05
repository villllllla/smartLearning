import type { WikiSummary } from "@/api/types";

/** Label for wiki list/detail badges; count matches latest batch preview. */
export function formatWikiPendingLabel(w: WikiSummary): string | null {
  const latest = w.pending_candidate_count ?? 0;
  const total = w.pending_candidate_total ?? latest;
  if (latest <= 0 && total <= 0) return null;
  if (total > latest) return `候选 ${latest}（共 ${total}）`;
  return `候选 ${latest}`;
}

export function wikiHasPending(w: WikiSummary): boolean {
  return (w.pending_candidate_total ?? w.pending_candidate_count ?? 0) > 0;
}
