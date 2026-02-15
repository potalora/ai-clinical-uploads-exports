"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { TimelineResponse, TimelineEvent } from "@/types/api";
import { RECORD_TYPE_COLORS, RECORD_TYPE_SHORT, DEFAULT_RECORD_COLOR } from "@/lib/constants";
import { GlowText } from "@/components/retro/GlowText";
import { RetroBadge } from "@/components/retro/RetroBadge";
import { RetroLoadingState } from "@/components/retro/RetroLoadingState";
import { RecordDetailSheet } from "@/components/retro/RecordDetailSheet";

const FILTER_TYPES = [
  { value: "", label: "ALL" },
  { value: "condition", label: "COND" },
  { value: "observation", label: "OBS" },
  { value: "medication", label: "MED" },
  { value: "encounter", label: "ENC" },
  { value: "immunization", label: "IMMUN" },
  { value: "procedure", label: "PROC" },
  { value: "document", label: "DOC" },
  { value: "imaging", label: "IMG" },
  { value: "allergy", label: "ALRG" },
];

function groupByMonth(events: TimelineEvent[]): { label: string; events: TimelineEvent[] }[] {
  const groups: Map<string, TimelineEvent[]> = new Map();
  for (const event of events) {
    const key = event.effective_date
      ? (() => {
          const d = new Date(event.effective_date);
          return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
        })()
      : "undated";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(event);
  }
  const sorted = Array.from(groups.entries()).sort((a, b) => {
    if (a[0] === "undated") return 1;
    if (b[0] === "undated") return -1;
    return b[0].localeCompare(a[0]);
  });
  return sorted.map(([key, events]) => {
    if (key === "undated") return { label: "Undated", events };
    const [y, m] = key.split("-");
    const months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];
    return { label: `${months[parseInt(m) - 1]} ${y}`, events };
  });
}

export default function TimelinePage() {
  const [data, setData] = useState<TimelineResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [selectedRecord, setSelectedRecord] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    let endpoint = "/timeline?limit=200";
    if (filter) endpoint += `&record_type=${filter}`;

    api
      .get<TimelineResponse>(endpoint)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [filter]);

  const events: TimelineEvent[] = data?.events || [];
  const sortedEvents = [...events].sort((a, b) => {
    if (!a.effective_date && !b.effective_date) return 0;
    if (!a.effective_date) return 1;
    if (!b.effective_date) return -1;
    return new Date(b.effective_date).getTime() - new Date(a.effective_date).getTime();
  });

  const groups = groupByMonth(sortedEvents);

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between gap-4">
        <GlowText as="h1">Timeline</GlowText>
        {data && (
          <span
            className="text-xs"
            style={{ color: "var(--theme-text-dim)" }}
          >
            {data.total} events
          </span>
        )}
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap gap-1">
        {FILTER_TYPES.map((ft) => {
          const active = filter === ft.value;
          return (
            <button
              key={ft.value}
              onClick={() => setFilter(ft.value)}
              className="px-3 py-1.5 text-xs font-medium transition-colors cursor-pointer rounded-md"
              style={{
                backgroundColor: active ? "var(--theme-amber)" : "var(--theme-bg-card)",
                color: active ? "var(--theme-bg-deep)" : "var(--theme-text-dim)",
                border: `1px solid ${active ? "var(--theme-amber)" : "var(--theme-border)"}`,
                fontFamily: "var(--font-body)",
              }}
              onMouseEnter={(e) => {
                if (!active) {
                  e.currentTarget.style.borderColor = "var(--theme-border-active)";
                  e.currentTarget.style.color = "var(--theme-text)";
                }
              }}
              onMouseLeave={(e) => {
                if (!active) {
                  e.currentTarget.style.borderColor = "var(--theme-border)";
                  e.currentTarget.style.color = "var(--theme-text-dim)";
                }
              }}
            >
              {ft.label}
            </button>
          );
        })}
      </div>

      {loading ? (
        <RetroLoadingState text="Loading timeline" />
      ) : sortedEvents.length === 0 ? (
        <div className="py-16 text-center">
          <p
            className="text-sm"
            style={{
              color: "var(--theme-text-muted)",
            }}
          >
            No events found
          </p>
          {filter && (
            <button
              onClick={() => setFilter("")}
              className="mt-3 text-xs cursor-pointer font-medium"
              style={{ color: "var(--theme-amber-dim)" }}
            >
              Clear filter
            </button>
          )}
        </div>
      ) : (
        <div className="relative pl-6">
          {/* Vertical line */}
          <div
            className="absolute left-2 top-0 bottom-0 w-px"
            style={{ backgroundColor: "var(--theme-amber-dim)" }}
          />

          {groups.map((group) => (
            <div key={group.label} className="mb-6">
              {/* Month/Year divider */}
              <div className="relative flex items-center gap-3 mb-3 -ml-6">
                <div
                  className="w-5 h-px"
                  style={{ backgroundColor: "var(--theme-amber-dim)" }}
                />
                <span
                  className="text-xs font-semibold"
                  style={{
                    color: "var(--theme-amber)",
                    fontFamily: "var(--font-body)",
                  }}
                >
                  {group.label}
                </span>
                <div
                  className="flex-1 h-px"
                  style={{ backgroundColor: "var(--theme-border)" }}
                />
              </div>

              {/* Events */}
              <div className="space-y-2">
                {group.events.map((event) => {
                  const colors = RECORD_TYPE_COLORS[event.record_type] || DEFAULT_RECORD_COLOR;
                  return (
                    <div
                      key={event.id}
                      className="relative flex items-start gap-3 cursor-pointer transition-colors"
                      onClick={() => setSelectedRecord(event.id)}
                      style={{ paddingLeft: "0.5rem" }}
                      onMouseEnter={(e) => {
                        const card = e.currentTarget.querySelector("[data-card]") as HTMLElement;
                        if (card) card.style.borderColor = "var(--theme-border-active)";
                      }}
                      onMouseLeave={(e) => {
                        const card = e.currentTarget.querySelector("[data-card]") as HTMLElement;
                        if (card) card.style.borderColor = "var(--theme-border)";
                      }}
                    >
                      {/* Dot on timeline */}
                      <div
                        className="absolute -left-[1.15rem] top-3 h-2 w-2 shrink-0"
                        style={{
                          backgroundColor: colors.dot,
                          borderRadius: "1px",
                          boxShadow: `0 0 4px ${colors.dot}40`,
                        }}
                      />

                      {/* Event card */}
                      <div
                        data-card
                        className="flex-1 border px-3 py-2 transition-colors"
                        style={{
                          backgroundColor: "var(--theme-bg-card)",
                          borderColor: "var(--theme-border)",
                          borderRadius: "4px",
                        }}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="space-y-0.5 min-w-0">
                            <div className="flex items-center gap-2">
                              <RetroBadge recordType={event.record_type} short />
                              <span
                                className="text-sm truncate"
                                style={{ color: "var(--theme-text)" }}
                              >
                                {event.display_text}
                              </span>
                            </div>
                            {event.code_display && (
                              <p
                                className="text-xs"
                                style={{ color: "var(--theme-text-dim)" }}
                              >
                                {event.code_display}
                              </p>
                            )}
                          </div>
                          <span
                            className="text-xs whitespace-nowrap shrink-0"
                            style={{ color: "var(--theme-text-muted)" }}
                          >
                            {event.effective_date
                              ? new Date(event.effective_date).toLocaleDateString()
                              : ""}
                          </span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      <RecordDetailSheet
        recordId={selectedRecord}
        open={!!selectedRecord}
        onClose={() => setSelectedRecord(null)}
      />
    </div>
  );
}
