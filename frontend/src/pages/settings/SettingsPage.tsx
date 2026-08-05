import { useState } from "react";
import {
  Bell,
  BrainCircuit,
  CalendarClock,
  Database,
  Newspaper,
  Settings as SettingsIcon,
  Sparkles,
  User,
  Zap,
} from "lucide-react";

import { PageHeader } from "@/components/layout/PageHeader";
import { cn } from "@/lib/utils";
import { AccountSection } from "./AccountSection";
import { AiNewsScheduleSection } from "./AiNewsScheduleSection";
import { DataAppearanceSection } from "./DataAppearanceSection";
import { FeishuTriggersSection } from "./FeishuTriggersSection";
import { PromptsSection } from "./PromptsSection";
import { ProvidersSection } from "./ProvidersSection";
import { PushScheduleSection } from "./PushScheduleSection";
import { ReviewScheduleSection } from "./ReviewScheduleSection";
import { TodoCheckSection } from "./TodoCheckSection";

type Tab =
  | "account"
  | "providers"
  | "prompts"
  | "push"
  | "review"
  | "ai-news"
  | "todo-check"
  | "feishu"
  | "data";

const TABS: { id: Tab; label: string; icon: typeof SettingsIcon }[] = [
  { id: "account", label: "账户", icon: User },
  { id: "providers", label: "模型与 Provider", icon: SettingsIcon },
  { id: "prompts", label: "Prompt 模板", icon: Sparkles },
  { id: "push", label: "定时推送", icon: Bell },
  { id: "review", label: "复习推送", icon: BrainCircuit },
  { id: "ai-news", label: "AI 资讯推送", icon: Newspaper },
  { id: "todo-check", label: "待办计划", icon: CalendarClock },
  { id: "feishu", label: "飞书触发", icon: Zap },
  { id: "data", label: "数据与外观", icon: Database },
];

export function SettingsPage() {
  const [tab, setTab] = useState<Tab>("account");

  return (
    <>
      <PageHeader
        title="设置"
        description="账户 · 模型与 Provider · Prompt 模板 · 定时推题 · 练习偏好 · 数据导入导出"
      />

      <div className="mx-auto max-w-5xl space-y-6 p-4 md:p-8">
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

        {tab === "account" && <AccountSection />}

        {tab === "providers" && <ProvidersSection />}

        {tab === "prompts" && <PromptsSection />}

        {tab === "push" && <PushScheduleSection />}

        {tab === "review" && <ReviewScheduleSection />}

        {tab === "ai-news" && <AiNewsScheduleSection />}

        {tab === "todo-check" && <TodoCheckSection />}

        {tab === "feishu" && <FeishuTriggersSection />}

        {tab === "data" && <DataAppearanceSection />}
      </div>
    </>
  );
}
