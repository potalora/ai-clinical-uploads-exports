"use client";

interface StatusItem {
  label: string;
  value: string | number;
}

interface StatusReadoutProps {
  items: StatusItem[];
}

export function StatusReadout({ items }: StatusReadoutProps) {
  return (
    <div
      className="flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 border rounded-lg text-sm"
      style={{
        backgroundColor: "var(--theme-bg-surface)",
        borderColor: "var(--theme-border)",
      }}
    >
      {items.map((item) => (
        <span key={item.label} className="flex items-center gap-2">
          <span
            className="text-xs font-medium"
            style={{ color: "var(--theme-text-dim)" }}
          >
            {item.label}:
          </span>
          <span
            className="font-medium"
            style={{ color: "var(--theme-text)" }}
          >
            {item.value}
          </span>
        </span>
      ))}
    </div>
  );
}
