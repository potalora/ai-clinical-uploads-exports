"use client";

import { cn } from "@/lib/utils";

export function RetroTable({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="overflow-auto">
      <table className={cn("w-full text-sm", className)}>{children}</table>
    </div>
  );
}

export function RetroTableHeader({ children }: { children: React.ReactNode }) {
  return (
    <thead>
      <tr
        className="border-b text-xs font-medium"
        style={{
          borderColor: "var(--theme-border)",
          color: "var(--theme-text-dim)",
        }}
      >
        {children}
      </tr>
    </thead>
  );
}

export function RetroTableHead({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <th className={cn("px-3 py-2 text-left font-medium", className)}>
      {children}
    </th>
  );
}

export function RetroTableBody({ children }: { children: React.ReactNode }) {
  return <tbody>{children}</tbody>;
}

export function RetroTableRow({
  className,
  onClick,
  children,
}: {
  className?: string;
  onClick?: () => void;
  children: React.ReactNode;
}) {
  return (
    <tr
      className={cn(
        "border-b transition-colors duration-150",
        onClick && "cursor-pointer",
        className,
      )}
      style={{ borderColor: "var(--theme-border)" }}
      onClick={onClick}
      onMouseEnter={(e) => {
        e.currentTarget.style.backgroundColor = "var(--theme-bg-card-hover)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.backgroundColor = "transparent";
      }}
    >
      {children}
    </tr>
  );
}

export function RetroTableCell({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <td
      className={cn("px-3 py-2", className)}
      style={{ color: "var(--theme-text)" }}
    >
      {children}
    </td>
  );
}
