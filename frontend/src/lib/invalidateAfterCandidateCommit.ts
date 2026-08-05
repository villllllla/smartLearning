import type { QueryClient } from "@tanstack/react-query";

/** Refresh lists after candidates are committed to the bank. */
export function invalidateAfterCandidateCommit(qc: QueryClient, batchId?: string) {
  qc.invalidateQueries({ queryKey: ["bank-questions"] });
  qc.invalidateQueries({ queryKey: ["candidate-batches"] });
  qc.invalidateQueries({ queryKey: ["wikis"] });
  qc.invalidateQueries({ queryKey: ["wiki"] });
  if (batchId) {
    qc.invalidateQueries({ queryKey: ["candidates", batchId] });
  }
}
