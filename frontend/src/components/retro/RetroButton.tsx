"use client";

import { cn } from "@/lib/utils";

interface RetroButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "ghost" | "destructive" | "large";
  children: React.ReactNode;
}

const variantStyles: Record<string, React.CSSProperties> = {
  primary: {
    backgroundColor: "var(--theme-amber)",
    color: "#ffffff",
  },
  ghost: {
    backgroundColor: "transparent",
    color: "var(--theme-amber)",
    border: "1px solid var(--theme-border)",
  },
  destructive: {
    backgroundColor: "var(--theme-terracotta)",
    color: "#ffffff",
  },
  large: {
    backgroundColor: "var(--theme-amber)",
    color: "#ffffff",
  },
};

export function RetroButton({
  variant = "primary",
  className,
  children,
  disabled,
  ...props
}: RetroButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center font-medium transition-all duration-200 cursor-pointer rounded-md",
        variant === "large"
          ? "px-8 py-3 text-sm"
          : "px-4 py-2 text-xs",
        disabled && "opacity-50 cursor-not-allowed",
        className,
      )}
      style={{
        ...variantStyles[variant],
        fontFamily: "var(--font-body)",
      }}
      disabled={disabled}
      onMouseEnter={(e) => {
        if (disabled) return;
        if (variant === "ghost") {
          e.currentTarget.style.backgroundColor = "var(--theme-bg-card-hover)";
          e.currentTarget.style.borderColor = "var(--theme-border-active)";
        } else {
          e.currentTarget.style.filter = "brightness(1.1)";
        }
      }}
      onMouseLeave={(e) => {
        if (disabled) return;
        if (variant === "ghost") {
          e.currentTarget.style.backgroundColor = "transparent";
          e.currentTarget.style.borderColor = "var(--theme-border)";
        } else {
          e.currentTarget.style.filter = "none";
        }
      }}
      {...props}
    >
      {children}
    </button>
  );
}
