import { useState } from "react";
import { LayoutDashboard, Settings2 } from "lucide-react";

import { PageHeader } from "@/components/layout/PageHeader";
import { cn } from "@/lib/utils";

import { GoalsManageTab } from "./GoalsManageTab";
import { GoalsOverviewTab } from "./GoalsOverviewTab";

type Tab = "overview" | "manage";

const TABS: { id: Tab; label: string; icon: typeof LayoutDashboard }[] = [
  { id: "overview", label: "进展概览", icon: LayoutDashboard },
  { id: "manage", label: "目标管理", icon: Settings2 },
];

export function GoalsPage() {
  const [tab, setTab] = useState<Tab>("overview");
  const [focusGoalId, setFocusGoalId] = useState<number | null>(null);

  return (
    <>
      <PageHeader
        title="求职目标"
        description="设定目标岗位，追踪掌握度，并在管理区域增删改查你的求职目标"
      />

      <div className="mx-auto max-w-3xl space-y-6 p-4 md:p-8">
        <div className="flex flex-wrap gap-2 border-b">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={cn(
                "flex items-center gap-2 border-b-2 px-3 py-2 text-sm font-medium transition-colors",
                tab === t.id
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              <t.icon className="h-4 w-4" />
              {t.label}
            </button>
          ))}
        </div>

        {tab === "overview" ? (
          <GoalsOverviewTab
            focusGoalId={focusGoalId}
            onClearFocus={() => setFocusGoalId(null)}
            onGoManage={() => setTab("manage")}
          />
        ) : (
          <GoalsManageTab
            onViewProgress={(goalId) => {
              setFocusGoalId(goalId);
              setTab("overview");
            }}
          />
        )}
      </div>
    </>
  );
}
