"use client";

import React from "react";
import { DetailRow, StatusBadge, str, nested, formatDate } from "./shared";

export function ImmunizationRenderer({ r }: { r: Record<string, unknown> }) {
  const name =
    str(nested(r, "vaccineCode", "text")) ||
    str(nested(r, "code", "text")) ||
    str(nested(r, "vaccineCode", "coding", "0", "display")) ||
    "";
  const date = formatDate(r.occurrenceDateTime ?? r.date);
  const dose = str(nested(r, "doseQuantity", "value"));
  const doseUnit = str(nested(r, "doseQuantity", "unit"));
  const route = str(nested(r, "route", "text")) || str(nested(r, "route", "coding", "0", "display"));
  const site = str(nested(r, "site", "text")) || str(nested(r, "site", "coding", "0", "display"));
  const manufacturer = str(nested(r, "manufacturer", "display"));
  const lotNumber = str(r.lotNumber);
  const status = str(r.status);

  return (
    <div className="space-y-3">
      {name && (
        <p
          className="text-sm font-semibold"
          style={{ color: "var(--theme-text)", fontFamily: "var(--font-body)" }}
        >
          {name}
        </p>
      )}

      <DetailRow label="Date" value={date} />

      {/* Compact grid: dose | route | site */}
      {(dose || route || site) && (
        <div
          className="grid grid-cols-3 gap-2 px-3 py-2 rounded-md text-xs"
          style={{ backgroundColor: "var(--record-immunization-bg)" }}
        >
          {dose && (
            <div>
              <div className="text-[10px]" style={{ color: "var(--theme-text-muted)" }}>Dose</div>
              <div style={{ color: "var(--theme-text)" }}>{dose}{doseUnit ? ` ${doseUnit}` : ""}</div>
            </div>
          )}
          {route && (
            <div>
              <div className="text-[10px]" style={{ color: "var(--theme-text-muted)" }}>Route</div>
              <div style={{ color: "var(--theme-text)" }}>{route}</div>
            </div>
          )}
          {site && (
            <div>
              <div className="text-[10px]" style={{ color: "var(--theme-text-muted)" }}>Site</div>
              <div style={{ color: "var(--theme-text)" }}>{site}</div>
            </div>
          )}
        </div>
      )}

      {/* Manufacturer + lot in monospace */}
      {(manufacturer || lotNumber) && (
        <div className="flex items-center gap-3 text-xs">
          {manufacturer && <DetailRow label="Mfr" value={manufacturer} />}
          {lotNumber && (
            <div className="flex items-baseline gap-1.5">
              <span style={{ color: "var(--theme-text-muted)" }}>Lot</span>
              <span
                style={{ fontFamily: "var(--font-mono)", fontSize: "13px", color: "var(--theme-text)" }}
              >
                {lotNumber}
              </span>
            </div>
          )}
        </div>
      )}

      {status && (
        <div className="pt-1">
          <StatusBadge label={status} />
        </div>
      )}
    </div>
  );
}
