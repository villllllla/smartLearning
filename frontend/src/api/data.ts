import { api } from "./client";

export type ClearScope =
  | "chats"
  | "attempts"
  | "candidates"
  | "questions"
  | "all";

export interface ClearResponse {
  deleted: Record<string, number>;
}

export const dataApi = {
  exportBank: (format: "json" | "csv") => {
    const today = new Date().toISOString().slice(0, 10).replace(/-/g, "");
    return api.download(
      `/data/export/bank?format=${format}`,
      `bank-${today}.${format}`,
    );
  },
  exportWikis: () => {
    const today = new Date().toISOString().slice(0, 10).replace(/-/g, "");
    return api.download(`/data/export/wikis`, `wikis-${today}.zip`);
  },
  clear: (scope: ClearScope) =>
    api.post<ClearResponse>("/data/clear", { scope }),
};
