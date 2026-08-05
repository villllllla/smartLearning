import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function MasteryBar({
  label,
  mastery,
  expected,
  coverage,
  lowCoverage,
}: {
  label: string;
  mastery: number;
  expected: number;
  coverage: number;
  lowCoverage: boolean;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium">{label}</span>
        <span className="text-muted-foreground">
          {mastery}% / 目标 {expected}%
          {lowCoverage ? (
            <Badge variant="outline" className="ml-2 text-[10px]">
              覆盖不足
            </Badge>
          ) : null}
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-muted">
        <div
          className={cn(
            "h-full rounded-full transition-all",
            mastery >= expected
              ? "bg-emerald-500"
              : mastery >= expected - 15
                ? "bg-amber-500"
                : "bg-rose-500",
          )}
          style={{ width: `${Math.min(100, mastery)}%` }}
        />
      </div>
      <div className="text-[11px] text-muted-foreground">
        题库覆盖 {Math.round(coverage * 100)}%
      </div>
    </div>
  );
}
