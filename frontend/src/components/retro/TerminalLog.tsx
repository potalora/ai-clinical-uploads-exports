"use client";

import { RECORD_TYPE_SHORT, RECORD_TYPE_COLORS, DEFAULT_RECORD_COLOR } from "@/lib/constants";

interface LogEntry {
  id: string;
  timestamp: string | null;
  recordType: string;
  text: string;
}

interface TerminalLogProps {
  entries: LogEntry[];
  onClickEntry?: (id: string) => void;
}

function formatTimestamp(dateStr: string | null): string {
  if (!dateStr) return "--";
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function TerminalLog({ entries, onClickEntry }: TerminalLogProps) {
  if (entries.length === 0) {
    return (
      <div className="py-8 text-center">
        <span
          className="text-sm"
          style={{ color: "var(--theme-text-muted)" }}
        >
          No entries yet
        </span>
      </div>
    );
  }

  return (
    <div className="space-y-0">
      {entries.map((entry) => {
        const colors = RECORD_TYPE_COLORS[entry.recordType] || DEFAULT_RECORD_COLOR;
        const shortType = RECORD_TYPE_SHORT[entry.recordType] || entry.recordType.toUpperCase().slice(0, 4);
        return (
          <div
            key={entry.id}
            className="flex items-start gap-3 py-2 border-b transition-colors duration-150"
            style={{
              borderColor: "var(--theme-border)",
              cursor: onClickEntry ? "pointer" : undefined,
            }}
            onClick={() => onClickEntry?.(entry.id)}
            onMouseEnter={(e) => {
              if (onClickEntry) e.currentTarget.style.backgroundColor = "var(--theme-bg-card-hover)";
            }}
            onMouseLeave={(e) => {
              if (onClickEntry) e.currentTarget.style.backgroundColor = "transparent";
            }}
          >
            <span
              className="text-xs shrink-0 font-mono"
              style={{ color: "var(--theme-text-muted)" }}
            >
              {formatTimestamp(entry.timestamp)}
            </span>
            <span
              className="text-xs font-medium shrink-0 px-1.5 py-0.5 rounded"
              style={{
                backgroundColor: colors.bg,
                color: colors.text,
                minWidth: "3rem",
                textAlign: "center",
              }}
            >
              {shortType}
            </span>
            <span
              className="text-sm truncate"
              style={{ color: "var(--theme-text)" }}
            >
              {entry.text}
            </span>
          </div>
        );
      })}
    </div>
  );
}
