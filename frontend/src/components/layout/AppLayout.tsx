import { NavLink, Outlet } from "react-router-dom";
import {
  BookOpen,
  BrainCircuit,
  ListTodo,
  LogOut,
  MessagesSquare,
  Library,
  GraduationCap,
  Monitor,
  Moon,
  Newspaper,
  Settings,
  Sun,
  Target,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  BulkGenerateProgressBar,
  useBulkGenerateLayoutPad,
} from "@/components/BulkGenerateProgressBar";
import { ToastViewport } from "@/components/ui/toast";
import { useAuth } from "@/lib/AuthContext";
import { useTheme, type Theme } from "@/lib/theme";

const NAV = [
  { to: "/wiki", label: "知识", short: "知识", icon: BookOpen },
  { to: "/chat", label: "对话", short: "对话", icon: MessagesSquare },
  { to: "/bank", label: "题库", short: "题库", icon: Library },
  { to: "/practice", label: "练习", short: "练习", icon: GraduationCap },
  { to: "/learning", label: "学习日志", short: "日志", icon: BrainCircuit },
  { to: "/ai-news", label: "AI 资讯", short: "资讯", icon: Newspaper },
  { to: "/todos", label: "待办", short: "待办", icon: ListTodo },
  { to: "/goals", label: "目标", short: "目标", icon: Target },
  { to: "/settings", label: "设置", short: "设置", icon: Settings },
];

export function AppLayout() {
  const bulkPad = useBulkGenerateLayoutPad();
  const { user, logout, authEnabled } = useAuth();

  return (
    <div className="flex h-full flex-col md:flex-row">
      {/* Desktop side nav */}
      <aside className="hidden md:flex w-56 shrink-0 flex-col border-r bg-card/40 p-4">
        <div className="mb-6 px-2">
          <div className="text-lg font-bold tracking-tight">SmartLearning</div>
          <div className="text-xs text-muted-foreground">
            知识 · 题库 · 刻意练习
          </div>
        </div>
        <nav className="flex flex-col gap-1">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground",
                )
              }
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto space-y-2 px-1 pt-4">
          {authEnabled && user && user.id > 0 ? (
            <div className="rounded-md border bg-background/60 px-3 py-2">
              <div className="truncate text-xs font-medium">{user.display_name || user.email}</div>
              <div className="truncate text-[11px] text-muted-foreground">{user.tenant_name}</div>
              <button
                type="button"
                onClick={() => {
                  logout();
                  window.location.href = "/login";
                }}
                className="mt-2 flex w-full items-center gap-2 rounded-md px-1 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <LogOut className="h-3.5 w-3.5" />
                退出登录
              </button>
            </div>
          ) : null}
          <ThemeQuickToggle />
          <div className="px-2 text-xs text-muted-foreground">
            v0.1.0 · 一期 MVP
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className={cn("flex-1 min-w-0 overflow-y-auto pb-20 md:pb-0", bulkPad)}>
        <Outlet />
      </main>

      {/* Mobile bottom tab */}
      <nav
        className="md:hidden fixed inset-x-0 bottom-0 z-40 grid grid-cols-6 border-t bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/70"
        aria-label="主导航"
      >
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              cn(
                "flex flex-col items-center justify-center gap-0.5 py-2 text-[11px] transition-colors",
                isActive ? "text-primary" : "text-muted-foreground",
              )
            }
          >
            <item.icon className="h-5 w-5" />
            <span>{item.short}</span>
          </NavLink>
        ))}
      </nav>

      <BulkGenerateProgressBar />
      <ToastViewport />
    </div>
  );
}

function ThemeQuickToggle() {
  const { theme, setTheme } = useTheme();
  const order: Theme[] = ["light", "dark", "system"];
  const idx = order.indexOf(theme);
  const next = order[(idx + 1) % order.length];
  const Icon = theme === "light" ? Sun : theme === "dark" ? Moon : Monitor;
  const label =
    theme === "light" ? "浅色" : theme === "dark" ? "深色" : "跟随系统";
  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      title={`主题：${label}（点击切换到 ${
        next === "light" ? "浅色" : next === "dark" ? "深色" : "跟随系统"
      }）`}
      className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
    >
      <Icon className="h-4 w-4" />
      <span>{label}</span>
    </button>
  );
}
