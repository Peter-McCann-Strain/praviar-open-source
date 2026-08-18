"use client";

import {
  AlertTriangle,
  CheckCircle,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { RISK_COLORS } from "@/lib/constants";
import type { RiskLevel } from "@praviar/shared-types";

const UNKNOWN_RISK_COLORS = {
  bg: "bg-[var(--surface-active)]",
  text: "text-[var(--text-secondary)]",
  border: "border-[var(--border-default)]",
} as const;

const RISK_ICONS: Record<string, typeof ShieldAlert> = {
  high: ShieldAlert,
  medium: AlertTriangle,
  low: ShieldCheck,
  clear: CheckCircle,
};

interface RiskBadgeProps {
  risk: RiskLevel;
  size?: "sm" | "md" | "lg";
  animated?: boolean;
  showIcon?: boolean;
  label?: string;
  className?: string;
}

export function RiskBadge({
  risk,
  size = "md",
  animated = false,
  showIcon = false,
  label,
  className,
}: RiskBadgeProps) {
  const riskKey = risk.toLowerCase() as keyof typeof RISK_COLORS;
  const colors = RISK_COLORS[riskKey] || UNKNOWN_RISK_COLORS;

  const sizeClasses = {
    sm: "px-2 py-0.5 text-xs",
    md: "px-2.5 py-0.5 text-xs",
    lg: "px-3.5 py-1.5 text-sm font-bold",
  };

  const iconSizes = {
    sm: "h-3 w-3",
    md: "h-3.5 w-3.5",
    lg: "h-4 w-4",
  };

  const Icon = RISK_ICONS[riskKey];

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full font-semibold uppercase tracking-wider tabular-nums",
        colors.bg,
        colors.text,
        `border ${colors.border}`,
        "shadow-[var(--shadow-xs)]",
        sizeClasses[size],
        animated && "ring-2 ring-current/10",
        className,
      )}
    >
      {showIcon && Icon && <Icon className={iconSizes[size]} />}
      {label ?? risk.toUpperCase()}
    </span>
  );
}
