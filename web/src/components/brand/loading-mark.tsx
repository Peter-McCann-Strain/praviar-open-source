"use client";

import { PraviarMarkFrame } from "@/components/brand/praviar-mark-frame";
import { cn } from "@/lib/utils";

interface LoadingMarkProps {
  text?: string;
  size?: "sm" | "md" | "lg";
}

export function LoadingMark({
  text = "Processing...",
  size = "md",
}: LoadingMarkProps) {
  const frameSize = { sm: "xs", md: "md", lg: "lg" } as const;
  const haloSize = { sm: "h-10 w-10", md: "h-14 w-14", lg: "h-16 w-16" };
  const textSize = { sm: "text-xs", md: "text-sm", lg: "text-base" };

  return (
    <div
      className="flex flex-col items-center gap-3"
      role="status"
      aria-live="polite"
      aria-label={text}
    >
      <div
        className={cn(
          "relative flex items-center justify-center",
          haloSize[size],
        )}
      >
        <span
          className="absolute inset-0 rounded-xl border border-brand-primary/20 bg-brand-primary/6 animate-pulse motion-reduce:animate-none"
          aria-hidden="true"
        />
        <span
          className="absolute -bottom-0.5 left-1/2 h-1 w-2/3 -translate-x-1/2 rounded-full bg-brand-secondary/60 animate-pulse motion-reduce:animate-none"
          aria-hidden="true"
        />
        <PraviarMarkFrame size={frameSize[size]} />
      </div>
      <p
        className={`${textSize[size]} text-[var(--text-secondary)] animate-pulse motion-reduce:animate-none`}
      >
        {text}
      </p>
    </div>
  );
}
