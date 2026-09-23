import * as React from "react";
import { cn } from "@/lib/utils";

export function Badge({
  tone = "neutral",
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: "neutral" | "good" | "warn" | "bad" }) {
  const tones = {
    neutral: "border-neutral-700 text-neutral-300",
    good: "border-emerald-700 text-emerald-300",
    warn: "border-amber-700 text-amber-300",
    bad: "border-rose-800 text-rose-300",
  } as const;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium",
        tones[tone],
        className,
      )}
      {...props}
    />
  );
}
