"use client";

import React from "react";
import { DetailRow, str, obj, nested, formatDate } from "./shared";

export function ObservationVitalRenderer({ r }: { r: Record<string, unknown> }) {
  const name =
    str(nested(r, "code", "text")) ||
    str(nested(r, "code", "coding", "0", "display")) ||
    "";
  const valueQuantity = obj(r.valueQuantity);
  const valueNum = str(valueQuantity.value);
  const valueUnit = str(valueQuantity.unit);
  const valueString = str(r.valueString);
  const displayValue = valueNum || valueString;
  const effectiveDate = formatDate(r.effectiveDateTime);

  // Check for component values (e.g., blood pressure systolic/diastolic)
  const components = Array.isArray(r.component) ? (r.component as Record<string, unknown>[]) : [];
  const hasComponents = components.length > 0 && !displayValue;

  return (
    <div className="space-y-3">
      {name && (
        <p className="text-[13px] font-medium" style={{ color: "var(--theme-text-muted)" }}>
          {name}
        </p>
      )}

      {displayValue && (
        <div className="flex items-baseline gap-2">
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "24px",
              lineHeight: 1,
              color: "var(--theme-amber)",
            }}
          >
            {displayValue}
          </span>
          {valueUnit && (
            <span className="text-xs" style={{ color: "var(--theme-text-muted)" }}>
              {valueUnit}
            </span>
          )}
        </div>
      )}

      {/* Component values (BP, etc.) */}
      {hasComponents && (
        <div className="flex items-baseline gap-1">
          {components.map((comp, i) => {
            const compName = str(nested(comp as Record<string, unknown>, "code", "text")) ||
              str(nested(comp as Record<string, unknown>, "code", "coding", "0", "display"));
            const compVal = str(nested(comp as Record<string, unknown>, "valueQuantity", "value"));
            const compUnit = str(nested(comp as Record<string, unknown>, "valueQuantity", "unit"));
            if (!compVal) return null;
            return (
              <React.Fragment key={i}>
                {i > 0 && (
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "18px",
                      color: "var(--theme-text-muted)",
                    }}
                  >
                    /
                  </span>
                )}
                <div className="flex items-baseline gap-1" title={compName}>
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "24px",
                      lineHeight: 1,
                      color: "var(--theme-amber)",
                    }}
                  >
                    {compVal}
                  </span>
                  {i === components.length - 1 && compUnit && (
                    <span className="text-xs" style={{ color: "var(--theme-text-muted)" }}>
                      {compUnit}
                    </span>
                  )}
                </div>
              </React.Fragment>
            );
          })}
        </div>
      )}

      <DetailRow label="Date" value={effectiveDate} />
    </div>
  );
}
