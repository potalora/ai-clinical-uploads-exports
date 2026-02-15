"use client";

import { cn } from "@/lib/utils";

interface RetroInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
}

export function RetroInput({ label, className, id, ...props }: RetroInputProps) {
  return (
    <div className="space-y-1.5">
      {label && (
        <label
          htmlFor={id}
          className="text-xs font-medium"
          style={{ color: "var(--theme-text-dim)" }}
        >
          {label}
        </label>
      )}
      <input
        id={id}
        className={cn(
          "w-full px-3 py-2 text-sm border rounded-md outline-none transition-colors duration-200",
          className,
        )}
        style={{
          backgroundColor: "var(--theme-bg-deep)",
          color: "var(--theme-text)",
          borderColor: "var(--theme-border)",
        }}
        onFocus={(e) => {
          e.currentTarget.style.borderColor = "var(--theme-amber)";
          e.currentTarget.style.boxShadow = "0 0 0 2px var(--theme-bg-deep), 0 0 0 4px var(--theme-amber)";
        }}
        onBlur={(e) => {
          e.currentTarget.style.borderColor = "var(--theme-border)";
          e.currentTarget.style.boxShadow = "none";
        }}
        {...props}
      />
    </div>
  );
}
