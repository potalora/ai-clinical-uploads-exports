"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import type { HealthRecord } from "@/types/api";
import { GlowText } from "@/components/retro/GlowText";
import { RetroBadge } from "@/components/retro/RetroBadge";
import { RetroCard, RetroCardHeader, RetroCardContent } from "@/components/retro/RetroCard";
import { RetroButton } from "@/components/retro/RetroButton";
import { RetroLoadingState } from "@/components/retro/RetroLoadingState";

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

  if (loading) return <RetroLoadingState text="Loading record" />;

  if (error || !record) {
    return (
      <div className="space-y-4">
        <Link
          href="/admin?tab=all"
          className="text-xs font-medium"
          style={{ color: "var(--theme-amber-dim)" }}
        >
          Back to records
        </Link>
        <div className="py-12 text-center">
          <p className="text-xs" style={{ color: "var(--theme-text-muted)" }}>
            {error || "Record not found"}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 retro-stagger">
      <Link
        href="/admin?tab=all"
        className="text-xs font-medium inline-block"
        style={{ color: "var(--theme-amber-dim)" }}
      >
        Back to records
      </Link>

      <div className="flex items-center gap-3">
        <GlowText as="h1">{record.display_text}</GlowText>
        <RetroBadge recordType={record.record_type} />
      </div>

      <p className="text-xs" style={{ color: "var(--theme-text-dim)" }}>
        {record.fhir_resource_type} record from {record.source_format}
      </p>

      <RetroCard accentTop>
        <RetroCardHeader>
          <GlowText as="h4" glow={false}>Record details</GlowText>
        </RetroCardHeader>
        <RetroCardContent>
          <dl className="space-y-2">
            <DetailRow label="Record type" value={record.record_type} />
            <DetailRow label="FHIR resource type" value={record.fhir_resource_type} />
            <DetailRow
              label="Effective date"
              value={
                record.effective_date
                  ? new Date(record.effective_date).toLocaleDateString("en-US", {
                      year: "numeric",
                      month: "long",
                      day: "numeric",
                    })
                  : "Not specified"
              }
            />
            {record.status && <DetailRow label="Status" value={record.status} />}
            <DetailRow label="Source format" value={record.source_format} />
            {record.code_system && <DetailRow label="Code system" value={record.code_system} mono />}
            {record.code_value && <DetailRow label="Code value" value={record.code_value} mono />}
            {record.code_display && <DetailRow label="Code display" value={record.code_display} />}
            {record.category && record.category.length > 0 && (
              <DetailRow label="Categories" value={record.category.join(", ")} />
            )}
            <DetailRow label="Created" value={new Date(record.created_at).toLocaleString()} />
          </dl>
        </RetroCardContent>
      </RetroCard>

      <RetroCard>
        <RetroCardHeader>
          <div className="flex items-center justify-between">
            <GlowText as="h4" glow={false}>FHIR Resource (JSON)</GlowText>
            <RetroButton variant="ghost" onClick={() => setShowFhir(!showFhir)}>
              {showFhir ? "Hide" : "Show"} FHIR JSON
            </RetroButton>
          </div>
        </RetroCardHeader>
        {showFhir && (
          <RetroCardContent>
            <pre
              className="text-xs overflow-auto max-h-96 p-4"
              style={{
                backgroundColor: "var(--theme-bg-deep)",
                color: "var(--theme-text-dim)",
                borderRadius: "4px",
                border: "1px solid var(--theme-border)",
              }}
            >
              {JSON.stringify(record.fhir_resource, null, 2)}
            </pre>
          </RetroCardContent>
        )}
      </RetroCard>
    </div>
  );
}

function DetailRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div
      className="flex justify-between py-1.5 border-b"
      style={{ borderColor: "var(--theme-border)" }}
    >
      <dt className="text-xs font-medium" style={{ color: "var(--theme-text-muted)" }}>
        {label}
      </dt>
      <dd
        className={`text-xs ${mono ? "font-mono" : "font-medium"}`}
        style={{ color: "var(--theme-text)" }}
      >
        {value}
      </dd>
    </div>
  );
}
