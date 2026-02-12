"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { api } from "@/lib/api";
import type { HealthRecord } from "@/types/api";

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

export default function RecordDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const [record, setRecord] = useState<HealthRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showFhir, setShowFhir] = useState(false);

  useEffect(() => {
    if (!id) return;

    setLoading(true);
    api
      .get<HealthRecord>(`/records/${id}`)
      .then(setRecord)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load record"))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-muted-foreground">Loading record...</p>
      </div>
    );
  }

  if (error || !record) {
    return (
      <div className="space-y-4">
        <Link href="/records" className="text-sm text-primary hover:underline">
          Back to Records
        </Link>
        <div className="text-center py-12">
          <p className="text-muted-foreground">{error || "Record not found."}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/records" className="text-sm text-primary hover:underline">
          Back to Records
        </Link>
      </div>

      <div>
        <div className="flex items-center gap-3 mb-2">
          <h1 className="text-3xl font-bold tracking-tight">{record.display_text}</h1>
          <span
            className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
              TYPE_COLORS[record.record_type] || "bg-gray-100 text-gray-800"
            }`}
          >
            {record.record_type}
          </span>
        </div>
        <p className="text-muted-foreground">
          {record.fhir_resource_type} record from {record.source_format}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Record Details</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="space-y-3">
            <div className="flex justify-between py-1.5 border-b">
              <dt className="text-sm text-muted-foreground">Record Type</dt>
              <dd className="text-sm font-medium">{record.record_type}</dd>
            </div>
            <div className="flex justify-between py-1.5 border-b">
              <dt className="text-sm text-muted-foreground">FHIR Resource Type</dt>
              <dd className="text-sm font-medium">{record.fhir_resource_type}</dd>
            </div>
            <div className="flex justify-between py-1.5 border-b">
              <dt className="text-sm text-muted-foreground">Effective Date</dt>
              <dd className="text-sm font-medium">
                {record.effective_date
                  ? new Date(record.effective_date).toLocaleDateString("en-US", {
                      year: "numeric",
                      month: "long",
                      day: "numeric",
                    })
                  : "Not specified"}
              </dd>
            </div>
            {record.status && (
              <div className="flex justify-between py-1.5 border-b">
                <dt className="text-sm text-muted-foreground">Status</dt>
                <dd className="text-sm font-medium">{record.status}</dd>
              </div>
            )}
            <div className="flex justify-between py-1.5 border-b">
              <dt className="text-sm text-muted-foreground">Source Format</dt>
              <dd className="text-sm font-medium">{record.source_format}</dd>
            </div>
            {record.code_system && (
              <div className="flex justify-between py-1.5 border-b">
                <dt className="text-sm text-muted-foreground">Code System</dt>
                <dd className="text-xs font-mono">{record.code_system}</dd>
              </div>
            )}
            {record.code_value && (
              <div className="flex justify-between py-1.5 border-b">
                <dt className="text-sm text-muted-foreground">Code Value</dt>
                <dd className="text-sm font-medium font-mono">{record.code_value}</dd>
              </div>
            )}
            {record.code_display && (
              <div className="flex justify-between py-1.5 border-b">
                <dt className="text-sm text-muted-foreground">Code Display</dt>
                <dd className="text-sm font-medium">{record.code_display}</dd>
              </div>
            )}
            {record.category && record.category.length > 0 && (
              <div className="flex justify-between py-1.5 border-b">
                <dt className="text-sm text-muted-foreground">Categories</dt>
                <dd className="text-sm font-medium">{record.category.join(", ")}</dd>
              </div>
            )}
            <div className="flex justify-between py-1.5">
              <dt className="text-sm text-muted-foreground">Created At</dt>
              <dd className="text-sm font-medium">
                {new Date(record.created_at).toLocaleString()}
              </dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>FHIR Resource (JSON)</CardTitle>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowFhir(!showFhir)}
            >
              {showFhir ? "Hide" : "Show"} Raw FHIR
            </Button>
          </div>
        </CardHeader>
        {showFhir && (
          <CardContent>
            <Separator className="mb-4" />
            <pre className="bg-muted p-4 rounded-md text-xs font-mono overflow-auto max-h-96">
              {JSON.stringify(record.fhir_resource, null, 2)}
            </pre>
          </CardContent>
        )}
      </Card>
    </div>
  );
}
