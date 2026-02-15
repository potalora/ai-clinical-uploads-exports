"use client";

import { RECORD_TYPE_COLORS, RECORD_TYPE_SHORT, DEFAULT_RECORD_COLOR } from "@/lib/constants";
import { cn } from "@/lib/utils";

interface RetroBadgeProps {
  recordType: string;
  short?: boolean;
  className?: string;
}

export function RetroBadge({ recordType, short = false, className }: RetroBadgeProps) {
  const colors = RECORD_TYPE_COLORS[recordType] || DEFAULT_RECORD_COLOR;
  const label = short
    ? (RECORD_TYPE_SHORT[recordType] || recordType.toUpperCase().slice(0, 4))
    : recordType;

  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-md",
        className,
      )}
      style={{
        backgroundColor: colors.bg,
        color: colors.text,
      }}
    >
      {label}
    </span>
  );
}
