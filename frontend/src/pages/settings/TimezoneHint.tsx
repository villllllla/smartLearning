import { useQuery } from "@tanstack/react-query";

import { settingsApi } from "@/api/settings";
import { timezonesApi } from "@/api/timezones";

/** Reminds that push schedules use the global timezone from 设置 → 账户. */
export function TimezoneHint() {
  const settingsQ = useQuery({
    queryKey: ["app-settings"],
    queryFn: () => settingsApi.get(),
  });
  const tzQ = useQuery({
    queryKey: ["timezones"],
    queryFn: () => timezonesApi.list(),
    staleTime: 60 * 60 * 1000,
  });
  const tz = settingsQ.data?.timezone;
  const label =
    tzQ.data?.items.find((t) => t.iana_name === tz)?.display_label ?? tz;

  return (
    <p className="text-xs text-muted-foreground">
      推送时间按账户「全局时区」执行
      {label ? `（${label}）` : ""}，请在 <span className="text-foreground">设置 → 账户</span>{" "}
      中修改。
    </p>
  );
}
