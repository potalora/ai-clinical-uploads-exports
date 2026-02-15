"use client";

import { cn } from "@/lib/utils";

interface GlowTextProps {
  as?: "h1" | "h2" | "h3" | "h4" | "h5" | "h6" | "span" | "p";
  glow?: boolean;
  className?: string;
  children: React.ReactNode;
}

const sizeMap: Record<string, string> = {
  h1: "text-2xl font-bold tracking-tight",
  h2: "text-xl font-semibold tracking-tight",
  h3: "text-lg font-semibold",
  h4: "text-base font-semibold",
  h5: "text-sm font-semibold",
  h6: "text-xs font-semibold",
  span: "",
  p: "",
};

export function GlowText({
  as: Tag = "h1",
  className,
  children,
}: GlowTextProps) {
  return (
    <Tag
      className={cn(sizeMap[Tag], className)}
      style={{
        fontFamily: "var(--font-body)",
        color: "var(--theme-text)",
      }}
    >
      {children}
    </Tag>
  );
}
