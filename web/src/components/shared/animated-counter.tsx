"use client";

import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "motion/react";

type CounterState = {
  display: number;
  status: "pending" | "animating" | "settled";
  target: number;
};

export function AnimatedCounter({
  value,
  duration = 1200,
  prefix = "",
  suffix = "",
  decimals = 0,
}: {
  value: number;
  duration?: number;
  prefix?: string;
  suffix?: string;
  decimals?: number;
}) {
  const prefersReducedMotion = useReducedMotion();
  const displayRef = useRef(0);
  const [counter, setCounter] = useState<CounterState>({
    display: 0,
    status: "pending",
    target: value,
  });
  const reducedMotion = prefersReducedMotion === true;
  const settlesImmediately = reducedMotion || duration <= 0;
  const isSettled =
    settlesImmediately ||
    (counter.status === "settled" && Object.is(counter.target, value));
  const observableStatus = isSettled
    ? "settled"
    : !Object.is(counter.target, value) || counter.status === "settled"
      ? "pending"
      : counter.status;
  const display = settlesImmediately ? value : counter.display;

  useEffect(() => {
    if (settlesImmediately) {
      displayRef.current = value;
      return;
    }

    const start = displayRef.current;
    const startTime = performance.now();
    let animationFrameId: number | null = null;
    let cancelled = false;

    function step(now: number) {
      if (cancelled) return;
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      const nextDisplay = start + (value - start) * eased;
      displayRef.current = nextDisplay;
      setCounter({
        display: nextDisplay,
        status: progress < 1 ? "animating" : "settled",
        target: value,
      });
      if (progress < 1) {
        animationFrameId = requestAnimationFrame(step);
      }
    }

    animationFrameId = requestAnimationFrame(step);

    return () => {
      cancelled = true;
      if (animationFrameId !== null) {
        cancelAnimationFrame(animationFrameId);
      }
    };
  }, [duration, settlesImmediately, value]);

  return (
    <span
      className={settlesImmediately ? undefined : "animate-count-up"}
      data-praviar-counter-state={observableStatus}
      data-praviar-counter-target={String(value)}
    >
      {prefix}
      {decimals > 0 ? display.toFixed(decimals) : Math.round(display)}
      {suffix}
    </span>
  );
}
