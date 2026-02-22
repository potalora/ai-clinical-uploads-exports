"use client";

import React from "react";
import { DetailRow, SectionDivider, str, nested, formatDate, arr, obj } from "./shared";

export function ConditionRenderer({ r }: { r: Record<string, unknown> }) {
  const name = str(nested(r, "code", "text")) || "";
  const clinicalStatus =
    str(nested(r, "clinicalStatus", "coding", "0", "code")) ||
    str(nested(r, "clinicalStatus", "text")) ||
    "";
  const onset = formatDate(r.onsetDateTime);
  const abatement = formatDate(r.abatementDateTime);
  const categoryText =
    str(nested(r, "category", "0", "text")) ||
    str(nested(r, "category", "0", "coding", "0", "display")) ||
    "";
  const notes = str(nested(r, "note", "0", "text"));
  const verificationStatus = str(nested(r, "verificationStatus", "coding", "0", "code"));

  const statusLower = clinicalStatus.toLowerCase();
  const statusConfig: Record<string, { bg: string; text: string; pulse: boolean }> = {
    active: { bg: "var(--theme-sage)", text: "var(--theme-bg-deep)", pulse: true },
    resolved: { bg: "var(--theme-text-muted)", text: "var(--theme-bg-deep)", pulse: false },
    inactive: { bg: "var(--theme-bg-deep)", text: "var(--theme-text-dim)", pulse: false },
    recurrence: { bg: "var(--theme-ochre)", text: "var(--theme-bg-deep)", pulse: true },
    remission: { bg: "var(--theme-text-dim)", text: "var(--theme-bg-deep)", pulse: false },
  };
  const config = statusConfig[statusLower] ?? { bg: "var(--theme-bg-deep)", text: "var(--theme-text)", pulse: false };

  // Category chip labels
  const categories = arr(r.category);
  const categoryChips: string[] = [];
  for (const cat of categories) {
    const text = str(obj(cat).text) || str(nested(obj(cat), "coding", "0", "display"));
    if (text) categoryChips.push(text);
  }

  return (
    <div className="space-y-3">
      {name && (
        <p
          className="text-base font-semibold"
          style={{ color: "var(--theme-text)", fontFamily: "var(--font-body)" }}
        >
          {name}
        </p>
      )}

      {/* Clinical status pill */}
      {clinicalStatus && (
        <div className="flex items-center gap-2">
          <span
            className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-full"
            style={{ backgroundColor: config.bg, color: config.text }}
          >
            {config.pulse && (
              <span
                className="w-1.5 h-1.5 rounded-full pulse-dot"
                style={{ backgroundColor: config.text, "--dot-color": config.text } as React.CSSProperties}
              />
            )}
            {clinicalStatus}
          </span>
          {verificationStatus && verificationStatus !== "confirmed" && (
            <span
              className="text-[11px] px-1.5 py-0.5 rounded"
              style={{ backgroundColor: "var(--theme-bg-deep)", color: "var(--theme-text-muted)" }}
            >
              {verificationStatus}
            </span>
          )}
        </div>
      )}

      {/* Timeline bar: onset → abatement */}
      {onset && (
        <div
          className="flex items-center gap-2 px-3 py-2 rounded-md text-xs"
          style={{ backgroundColor: "var(--theme-bg-deep)" }}
        >
          <span style={{ color: "var(--theme-text-muted)" }}>Onset</span>
          <span style={{ color: "var(--theme-text)" }}>{onset}</span>
          {abatement && (
            <>
              <span style={{ color: "var(--theme-text-muted)" }}>→</span>
              <span style={{ color: "var(--theme-text-muted)" }}>Resolved</span>
              <span style={{ color: "var(--theme-text)" }}>{abatement}</span>
            </>
          )}
        </div>
      )}

      {/* Category chips */}
      {categoryChips.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {categoryChips.map((chip) => (
            <span
              key={chip}
              className="px-2 py-0.5 text-[11px] font-medium rounded"
              style={{
                backgroundColor: "var(--record-condition-bg)",
                color: "var(--record-condition-text)",
              }}
            >
              {chip}
            </span>
          ))}
        </div>
      )}

      {categoryText && !categoryChips.includes(categoryText) && (
        <DetailRow label="Category" value={categoryText} />
      )}

      {/* Notes */}
      {notes && (
        <>
          <SectionDivider />
          <div
            className="px-3 py-2 rounded-md text-xs"
            style={{
              backgroundColor: "var(--theme-bg-deep)",
              color: "var(--theme-text-dim)",
              borderLeft: "2px solid var(--theme-border-active)",
            }}
          >
            {notes}
          </div>
        </>
      )}
    </div>
  );
}
