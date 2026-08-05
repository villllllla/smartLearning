import { useCallback, useRef, useState } from "react";

import { cn } from "@/lib/utils";

const STEPS = [0, 25, 50, 75, 100] as const;

function snapProgress(value: number): number {
  const p = Math.max(0, Math.min(100, value));
  return Math.round(p / 25) * 25;
}

function indexForProgress(p: number): number {
  return STEPS.indexOf(snapProgress(p) as (typeof STEPS)[number]);
}

export function TodoProgressSlider({
  value,
  disabled,
  onChange,
  className,
}: {
  value: number;
  disabled?: boolean;
  onChange: (progress: number) => void;
  className?: string;
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState(false);
  const [preview, setPreview] = useState<number | null>(null);

  const display = preview ?? snapProgress(value);
  const idx = indexForProgress(display);
  const pct = `${display}%`;

  const pickFromClientX = useCallback((clientX: number) => {
    const el = trackRef.current;
    if (!el) return 0;
    const rect = el.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    return snapProgress(Math.round(ratio * 100));
  }, []);

  const commit = (p: number) => {
    const snapped = snapProgress(p);
    setPreview(null);
    if (snapped !== snapProgress(value)) onChange(snapped);
  };

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (disabled) return;
    e.preventDefault();
    e.stopPropagation();
    trackRef.current?.setPointerCapture(e.pointerId);
    setDragging(true);
    setPreview(pickFromClientX(e.clientX));
  };

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragging || disabled) return;
    e.preventDefault();
    setPreview(pickFromClientX(e.clientX));
  };

  const onPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragging) return;
    e.preventDefault();
    trackRef.current?.releasePointerCapture(e.pointerId);
    setDragging(false);
    commit(pickFromClientX(e.clientX));
  };

  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
        <span className="shrink-0">进度</span>
        <span className="ml-auto shrink-0 tabular-nums font-medium text-foreground">
          {display}%
        </span>
      </div>
      <div
        ref={trackRef}
        role="slider"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={display}
        aria-disabled={disabled}
        className={cn(
          "relative h-3 w-full rounded-full bg-muted/80 select-none touch-none",
          disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer",
        )}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <div
          className={cn(
            "absolute inset-y-0 left-0 rounded-full bg-primary/35",
            !dragging && "transition-[width] duration-75",
          )}
          style={{ width: pct }}
        />
        {STEPS.map((step, i) => (
          <button
            key={step}
            type="button"
            disabled={disabled}
            tabIndex={-1}
            className={cn(
              "absolute top-1/2 z-10 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full border border-background/80",
              i <= idx ? "bg-primary" : "bg-muted-foreground/40",
              dragging ? "pointer-events-none" : "",
              disabled ? "pointer-events-none" : "",
            )}
            style={{ left: `${step}%` }}
            aria-label={`${step}%`}
            onClick={(e) => {
              e.stopPropagation();
              if (!disabled) onChange(step);
            }}
          />
        ))}
        <div
          className={cn(
            "absolute top-1/2 z-20 h-5 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background bg-foreground/90 shadow-md",
            !dragging && "transition-[left] duration-75",
          )}
          style={{ left: pct }}
        />
      </div>
    </div>
  );
}
