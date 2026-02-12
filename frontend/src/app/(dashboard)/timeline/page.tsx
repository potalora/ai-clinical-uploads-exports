"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { TimelineResponse, TimelineEvent } from "@/types/api";

const TYPE_COLORS: Record<string, string> = {
  condition: "bg-amber-100 text-amber-800",
  observation: "bg-teal-100 text-teal-800",
  medication: "bg-violet-100 text-violet-800",
  encounter: "bg-emerald-100 text-emerald-800",
  immunization: "bg-blue-100 text-blue-800",
  procedure: "bg-rose-100 text-rose-800",
  document: "bg-slate-100 text-slate-800",
  diagnostic_report: "bg-cyan-100 text-cyan-800",
  allergy: "bg-red-100 text-red-800",
  imaging: "bg-purple-100 text-purple-800",
};

const DOT_COLORS: Record<string, string> = {
  condition: "bg-amber-500",
  observation: "bg-teal-500",
  medication: "bg-violet-500",
  encounter: "bg-emerald-500",
  immunization: "bg-blue-500",
  procedure: "bg-rose-500",
  document: "bg-slate-500",
  diagnostic_report: "bg-cyan-500",
  allergy: "bg-red-500",
  imaging: "bg-purple-500",
};

const FILTER_TYPES = [
  { value: "", label: "All" },
  { value: "condition", label: "Conditions" },
  { value: "observation", label: "Observations" },
  { value: "medication", label: "Medications" },
  { value: "encounter", label: "Encounters" },
  { value: "immunization", label: "Immunizations" },
  { value: "procedure", label: "Procedures" },
  { value: "document", label: "Documents" },
  { value: "imaging", label: "Imaging" },
];

export default function TimelinePage() {
  const [data, setData] = useState<TimelineResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    setLoading(true);
    let endpoint = "/timeline";
    if (filter) endpoint += `?record_type=${filter}`;

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

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Timeline</h1>
        <p className="text-muted-foreground">
          Chronological view of all health records
          {data && ` (${data.total} events)`}
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {FILTER_TYPES.map((ft) => (
          <Button
            key={ft.value}
            variant={filter === ft.value ? "default" : "outline"}
            size="sm"
            onClick={() => setFilter(ft.value)}
          >
            {ft.label}
          </Button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-64">
          <p className="text-muted-foreground">Loading timeline...</p>
        </div>
      ) : sortedEvents.length === 0 ? (
        <Card>
          <CardContent className="py-12">
            <div className="text-center">
              <p className="text-muted-foreground">No events found.</p>
              {filter && (
                <Button variant="link" onClick={() => setFilter("")}>
                  Clear filter
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="relative">
          <div className="absolute left-4 top-0 bottom-0 w-px bg-border" />

          <div className="space-y-4">
            {sortedEvents.map((event) => (
              <div key={event.id} className="relative flex items-start gap-4 pl-10">
                <div
                  className={`absolute left-2.5 top-1.5 h-3 w-3 rounded-full ring-2 ring-background ${
                    DOT_COLORS[event.record_type] || "bg-gray-500"
                  }`}
                />
                <Card className="flex-1 py-3">
                  <CardContent className="py-0 px-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="space-y-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span
                            className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium shrink-0 ${
                              TYPE_COLORS[event.record_type] || "bg-gray-100 text-gray-800"
                            }`}
                          >
                            {event.record_type}
                          </span>
                          <Link
                            href={`/records/${event.id}`}
                            className="text-sm font-medium text-primary hover:underline truncate"
                          >
                            {event.display_text}
                          </Link>
                        </div>
                        {event.code_display && (
                          <p className="text-xs text-muted-foreground">{event.code_display}</p>
                        )}
                      </div>
                      <span className="text-xs text-muted-foreground whitespace-nowrap shrink-0">
                        {event.effective_date
                          ? new Date(event.effective_date).toLocaleDateString()
                          : "No date"}
                      </span>
                    </div>
                  </CardContent>
                </Card>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
