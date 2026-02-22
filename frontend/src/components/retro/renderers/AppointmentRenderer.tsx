"use client";

import React from "react";
import { DetailRow, str, arr, obj, nested, formatDateTime } from "./shared";

const STATUS_COLORS: Record<string, string> = {
  booked: "var(--theme-sage)",
  cancelled: "var(--theme-terracotta)",
  fulfilled: "var(--theme-ochre)",
  pending: "var(--theme-text-dim)",
  proposed: "var(--theme-text-dim)",
  noshow: "var(--theme-terracotta)",
};

export function AppointmentRenderer({ r }: { r: Record<string, unknown> }) {
  const description = str(r.description);
  const status = str(r.status);
  const start = formatDateTime(r.start);
  const end = formatDateTime(r.end);

  const participants = arr(r.participant);
  const participantEntries: Array<{ name: string; role: string }> = [];
  for (const p of participants) {
    const pObj = obj(p);
    const name = str(nested(pObj, "actor", "display"));
    const role =
      str(nested(pObj, "type", "0", "text")) ||
      str(nested(pObj, "type", "0", "coding", "0", "display")) ||
      "";
    if (name) participantEntries.push({ name, role });
  }

  const statusColor = STATUS_COLORS[status.toLowerCase()] ?? "var(--theme-bg-deep)";

  return (
    <div className="space-y-3">
      {description && (
        <p
          className="text-base font-semibold"
          style={{ color: "var(--theme-text)", fontFamily: "var(--font-body)" }}
        >
          {description}
        </p>
      )}

      {/* Status badge */}
      {status && (
        <span
          className="inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-md"
          style={{
            backgroundColor: statusColor,
            color: status.toLowerCase() === "booked" ? "var(--theme-bg-deep)" : "var(--theme-text)",
          }}
        >
          {status}
        </span>
      )}

      {/* Time display */}
      {start && (
        <div
          className="flex items-center gap-2 px-3 py-2 rounded-md text-xs"
          style={{ backgroundColor: "var(--record-appointment-bg)" }}
        >
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "16px",
              color: "var(--record-appointment-text)",
            }}
          >
            {start}
          </span>
          {end && (
            <>
              <span style={{ color: "var(--theme-text-muted)" }}>→</span>
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "16px",
                  color: "var(--record-appointment-text)",
                }}
              >
                {end}
              </span>
            </>
          )}
        </div>
      )}

      {/* Participants */}
      {participantEntries.length > 0 && (
        <div className="space-y-1">
          <span className="text-[10px] font-medium" style={{ color: "var(--theme-text-muted)" }}>
            Participants
          </span>
          {participantEntries.map((p, i) => (
            <div key={i} className="flex items-baseline justify-between gap-2 py-0.5">
              <span className="text-xs" style={{ color: "var(--theme-text)" }}>
                {p.name}
              </span>
              {p.role && (
                <span
                  className="text-[10px] px-1.5 py-0.5 rounded"
                  style={{
                    backgroundColor: "var(--theme-bg-deep)",
                    color: "var(--theme-text-muted)",
                  }}
                >
                  {p.role}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
