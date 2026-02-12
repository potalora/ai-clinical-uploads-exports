"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { DashboardOverview } from "@/types/api";
import Link from "next/link";

const TYPE_COLORS: Record<string, string> = {
  condition: "bg-amber-100 text-amber-800",
  observation: "bg-teal-100 text-teal-800",
  medication: "bg-violet-100 text-violet-800",
  encounter: "bg-emerald-100 text-emerald-800",
  immunization: "bg-blue-100 text-blue-800",
  procedure: "bg-rose-100 text-rose-800",
  document: "bg-slate-100 text-slate-800",
  diagnostic_report: "bg-cyan-100 text-cyan-800",
  service_request: "bg-orange-100 text-orange-800",
  communication: "bg-pink-100 text-pink-800",
  appointment: "bg-indigo-100 text-indigo-800",
  care_plan: "bg-lime-100 text-lime-800",
  imaging: "bg-purple-100 text-purple-800",
  allergy: "bg-red-100 text-red-800",
};

const TYPE_LABELS: Record<string, string> = {
  condition: "Conditions",
  observation: "Observations",
  medication: "Medications",
  encounter: "Encounters",
  immunization: "Immunizations",
  procedure: "Procedures",
  document: "Documents",
  diagnostic_report: "Diagnostic Reports",
  service_request: "Service Requests",
  communication: "Communications",
  appointment: "Appointments",
  care_plan: "Care Plans",
  imaging: "Imaging",
  allergy: "Allergies",
};

export default function DashboardPage() {
  const [data, setData] = useState<DashboardOverview | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<DashboardOverview>("/dashboard/overview")
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-muted-foreground">Loading dashboard...</div>
      </div>
    );
  }

  const overview = data || {
    total_records: 0,
    total_patients: 0,
    total_uploads: 0,
    records_by_type: {},
    recent_records: [],
    date_range_start: null,
    date_range_end: null,
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Overview of your health records
          {overview.date_range_start && overview.date_range_end && (
            <span className="ml-2">
              ({new Date(overview.date_range_start).getFullYear()} - {new Date(overview.date_range_end).getFullYear()})
            </span>
          )}
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Total Records</CardDescription>
            <CardTitle className="text-4xl">{overview.total_records}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground">
              {overview.total_uploads} upload{overview.total_uploads !== 1 ? "s" : ""}
            </p>
          </CardContent>
        </Card>
        {(["condition", "medication", "observation", "encounter"] as const).map((type) => (
          <Card key={type}>
            <CardHeader className="pb-2">
              <CardDescription>{TYPE_LABELS[type] || type}</CardDescription>
              <CardTitle className="text-4xl">{overview.records_by_type[type] || 0}</CardTitle>
            </CardHeader>
            <CardContent>
              <Link href={type === "observation" ? "/labs" : `/${type}s`} className="text-xs text-primary hover:underline">
                View all
              </Link>
            </CardContent>
          </Card>
        ))}
      </div>

      {Object.keys(overview.records_by_type).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Records by Category</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {Object.entries(overview.records_by_type)
                .sort(([, a], [, b]) => b - a)
                .map(([type, count]) => (
                  <span
                    key={type}
                    className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-medium ${TYPE_COLORS[type] || "bg-gray-100 text-gray-800"}`}
                  >
                    {TYPE_LABELS[type] || type}: {count}
                  </span>
                ))}
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Recent Records</CardTitle>
          <CardDescription>Last 10 records added</CardDescription>
        </CardHeader>
        <CardContent>
          {overview.recent_records.length === 0 ? (
            <div className="text-sm text-muted-foreground py-8 text-center">
              <p className="mb-2">No records yet.</p>
              <Link href="/upload" className="text-primary hover:underline">
                Upload your first health records
              </Link>
            </div>
          ) : (
            <div className="space-y-2">
              {overview.recent_records.map((r) => (
                <div
                  key={r.id}
                  className="flex items-center justify-between py-2 border-b last:border-0"
                >
                  <div className="flex items-center gap-3">
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${TYPE_COLORS[r.record_type] || "bg-gray-100"}`}
                    >
                      {r.record_type}
                    </span>
                    <span className="text-sm truncate max-w-md">{r.display_text}</span>
                  </div>
                  <span className="text-xs text-muted-foreground whitespace-nowrap">
                    {r.effective_date
                      ? new Date(r.effective_date).toLocaleDateString()
                      : "No date"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
