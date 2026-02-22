"use client";

import React from "react";
import { DetailRow, str, obj, arr, nested, formatDate } from "./shared";

export function ObservationLabRenderer({ r }: { r: Record<string, unknown> }) {
  const testName =
    str(nested(r, "code", "text")) ||
    str(nested(r, "code", "coding", "0", "display")) ||
    "";
  const valueQuantity = obj(r.valueQuantity);
  const valueNum = str(valueQuantity.value);
  const valueUnit = str(valueQuantity.unit);
  const valueString = str(r.valueString);
  const displayValue = valueNum ? `${valueNum}` : valueString;
  const displayUnit = valueUnit || "";
  const effectiveDate = formatDate(r.effectiveDateTime);

  const refRangeArr = arr(r.referenceRange);
  const refRange = obj(refRangeArr[0]);
  const refLow = str(nested(refRange, "low", "value"));
  const refHigh = str(nested(refRange, "high", "value"));
  const refUnit = str(nested(refRange, "low", "unit")) || str(nested(refRange, "high", "unit"));
  const refText = str(refRange.text) || (refLow || refHigh ? `${refLow || "?"} - ${refHigh || "?"} ${refUnit}` : "");

  const interpretationCode =
    str(nested(r, "interpretation", "0", "coding", "0", "code")) ||
    str(nested(r, "interpretation", "0", "text")) ||
    "";
  const interpUpper = interpretationCode.toUpperCase();

  let interpColor = "var(--theme-text-dim)";
  let interpLabel = interpretationCode;
  let gaugeColor = "var(--theme-sage)";
  if (interpUpper === "H" || interpUpper === "HH" || interpUpper === "HIGH") {
    interpColor = "var(--theme-terracotta)";
    interpLabel = interpUpper === "HH" ? "Critical High" : "High";
    gaugeColor = "var(--theme-terracotta)";
  } else if (interpUpper === "L" || interpUpper === "LL" || interpUpper === "LOW") {
    interpColor = "var(--record-procedure-text)";
    interpLabel = interpUpper === "LL" ? "Critical Low" : "Low";
    gaugeColor = "var(--record-procedure-text)";
  } else if (interpUpper === "N" || interpUpper === "NORMAL") {
    interpColor = "var(--theme-sage)";
    interpLabel = "Normal";
    gaugeColor = "var(--theme-sage)";
  }

  // Reference range gauge position
  const numVal = parseFloat(valueNum);
  const numLow = parseFloat(refLow);
  const numHigh = parseFloat(refHigh);
  const showGauge = !isNaN(numVal) && !isNaN(numLow) && !isNaN(numHigh) && numHigh > numLow;

  let gaugePercent = 50;
  if (showGauge) {
    const range = numHigh - numLow;
    const padding = range * 0.3;
    const minVal = numLow - padding;
    const maxVal = numHigh + padding;
    gaugePercent = Math.max(0, Math.min(100, ((numVal - minVal) / (maxVal - minVal)) * 100));
  }

  // Fill area (where the normal range is)
  let fillStart = 0;
  let fillWidth = 100;
  if (showGauge) {
    const range = numHigh - numLow;
    const padding = range * 0.3;
    const minVal = numLow - padding;
    const maxVal = numHigh + padding;
    fillStart = ((numLow - minVal) / (maxVal - minVal)) * 100;
    fillWidth = ((numHigh - minVal) / (maxVal - minVal)) * 100 - fillStart;
  }

  return (
    <div className="space-y-3">
      {testName && (
        <p className="text-[13px] font-medium" style={{ color: "var(--theme-text-muted)" }}>
          {testName}
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
          {displayUnit && (
            <span className="text-xs" style={{ color: "var(--theme-text-muted)" }}>
              {displayUnit}
            </span>
          )}
          {interpretationCode && (
            <span
              className="text-xs font-semibold ml-1 px-1.5 py-0.5 rounded"
              style={{ color: interpColor, backgroundColor: "var(--theme-bg-deep)" }}
            >
              {interpLabel}
            </span>
          )}
        </div>
      )}

      {/* Reference range gauge */}
      {showGauge && (
        <div className="space-y-1">
          <div className="range-gauge" style={{ width: "100%" }}>
            <div
              className="range-gauge-fill"
              style={{
                left: `${fillStart}%`,
                width: `${fillWidth}%`,
                backgroundColor: "var(--theme-sage)",
                opacity: 0.2,
              }}
            />
            <div
              className="range-gauge-indicator"
              style={{
                left: `${gaugePercent}%`,
                backgroundColor: gaugeColor,
              }}
            />
          </div>
          <div className="flex justify-between text-[11px]" style={{ color: "var(--theme-text-muted)" }}>
            <span>{refLow} {refUnit}</span>
            <span>{refHigh} {refUnit}</span>
          </div>
        </div>
      )}

      {!showGauge && refText && <DetailRow label="Reference" value={refText} mono />}

      {effectiveDate && <DetailRow label="Date" value={effectiveDate} />}
    </div>
  );
}
