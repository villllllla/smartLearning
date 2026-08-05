import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Globe, Loader2 } from "lucide-react";

import { settingsApi } from "@/api/settings";
import { timezonesApi } from "@/api/timezones";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { toast } from "@/components/ui/toast";

/** Global IANA timezone — drives todos, schedules, and reminder display. */
export function TimezoneSection() {
  const qc = useQueryClient();
  const settingsQ = useQuery({
    queryKey: ["app-settings"],
    queryFn: () => settingsApi.get(),
  });
  const timezonesQ = useQuery({
    queryKey: ["timezones"],
    queryFn: () => timezonesApi.list(),
    staleTime: 60 * 60 * 1000,
  });

  const [timezone, setTimezone] = useState("Asia/Shanghai");

  useEffect(() => {
    if (settingsQ.data?.timezone) setTimezone(settingsQ.data.timezone);
  }, [settingsQ.data?.timezone]);

  const save = useMutation({
    mutationFn: () => settingsApi.update({ timezone }),
    onSuccess: (data) => {
      qc.setQueryData(["app-settings"], data);
      qc.invalidateQueries({ queryKey: ["todos"] });
      qc.invalidateQueries({ queryKey: ["todo-calendar"] });
      qc.invalidateQueries({ queryKey: ["todo-check"] });
      qc.invalidateQueries({ queryKey: ["ai-news-schedule"] });
      toast.success("全局时区已保存");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const items = timezonesQ.data?.items ?? [];
  const selectValue = items.some((t) => t.iana_name === timezone)
    ? timezone
    : items.find((t) => t.iana_name === "Asia/Shanghai")?.iana_name ?? timezone;

  return (
    <Card>
      <CardContent className="space-y-3 p-6">
        <div className="flex items-center gap-2 text-base font-semibold">
          <Globe className="h-4 w-4 text-primary" />
          全局时区
        </div>
        <p className="text-xs text-muted-foreground">
          待办提醒、定时推送、复习推送、AI 资讯等均使用此时区；默认提醒 21:00。
        </p>
        <div className="flex max-w-md flex-wrap items-end gap-3">
          <div className="min-w-[220px] flex-1 space-y-1.5">
            <Label className="text-xs">时区</Label>
            {timezonesQ.isLoading ? (
              <div className="flex h-10 items-center text-sm text-muted-foreground">
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                加载中…
              </div>
            ) : (
              <Select value={selectValue} onChange={(e) => setTimezone(e.target.value)}>
                {items.map((tz) => (
                  <option key={tz.iana_name} value={tz.iana_name}>
                    {tz.display_label}
                  </option>
                ))}
              </Select>
            )}
          </div>
          <Button
            size="sm"
            onClick={() => save.mutate()}
            disabled={save.isPending || settingsQ.isLoading}
          >
            {save.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            保存
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
