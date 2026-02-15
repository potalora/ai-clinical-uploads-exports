"use client";

import { cn } from "@/lib/utils";

interface RetroCardProps {
  className?: string;
  accentTop?: boolean;
  children: React.ReactNode;
}

export function RetroCard({ className, accentTop, children }: RetroCardProps) {
  return (
    <div
      className={cn(
        "border rounded-lg transition-shadow duration-200 theme-shadow",
        className,
      )}
      style={{
        backgroundColor: "var(--theme-bg-card)",
        borderColor: "var(--theme-border)",
        borderTop: accentTop ? "2px solid var(--theme-amber)" : undefined,
      }}
    >
      {children}
    </div>
  );
}

export function RetroCardHeader({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn("px-4 py-3 border-b", className)}
      style={{ borderColor: "var(--theme-border)" }}
    >
      {children}
    </div>
  );
}

export function RetroCardContent({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return <div className={cn("px-4 py-4", className)}>{children}</div>;
}
