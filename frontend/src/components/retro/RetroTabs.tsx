"use client";

import { cn } from "@/lib/utils";

interface RetroTab {
  key: string;
  label: string;
  separator?: boolean;
}

interface RetroTabsProps {
  tabs: RetroTab[];
  active: string;
  onChange: (key: string) => void;
}

export function RetroTabs({ tabs, active, onChange }: RetroTabsProps) {
  return (
    <div
      className="flex items-center gap-0.5 overflow-x-auto border-b pb-px"
      style={{ borderColor: "var(--theme-border)" }}
    >
      {tabs.map((tab) => {
        if (tab.separator) return null;
        const isActive = active === tab.key;
        return (
          <button
            key={tab.key}
            onClick={() => onChange(tab.key)}
            className={cn(
              "relative px-3 py-2 text-xs font-medium transition-colors duration-200 whitespace-nowrap cursor-pointer",
            )}
            style={{
              color: isActive ? "var(--theme-amber)" : "var(--theme-text-dim)",
              fontFamily: "var(--font-body)",
            }}
            onMouseEnter={(e) => {
              if (!isActive) e.currentTarget.style.color = "var(--theme-text)";
            }}
            onMouseLeave={(e) => {
              if (!isActive) e.currentTarget.style.color = "var(--theme-text-dim)";
            }}
          >
            {tab.label}
            {isActive && (
              <span
                className="absolute bottom-0 left-1 right-1 h-0.5 rounded-full"
                style={{ backgroundColor: "var(--theme-amber)" }}
              />
            )}
          </button>
        );
      })}
    </div>
  );
}
