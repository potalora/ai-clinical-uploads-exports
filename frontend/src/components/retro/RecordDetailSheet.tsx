"use client";

import { useEffect, useState } from "react";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { api } from "@/lib/api";
import type { HealthRecord } from "@/types/api";
import { RetroBadge } from "./RetroBadge";
import { RetroLoadingState } from "./RetroLoadingState";

interface RecordDetailSheetProps {
  recordId: string | null;
  open: boolean;
  onClose: () => void;
}

export function RecordDetailSheet({ recordId, open, onClose }: RecordDetailSheetProps) {
  const [record, setRecord] = useState<HealthRecord | null>(null);
  const [loading, setLoading] = useState(false);
  const [showFhir, setShowFhir] = useState(false);

  useEffect(() => {
    if (!recordId || !open) {
      setRecord(null);
      setShowFhir(false);
      return;
    }

    setLoading(true);
    api
      .get<HealthRecord>(`/records/${recordId}`)
      .then(setRecord)
      .catch(() => setRecord(null))
      .finally(() => setLoading(false));
  }, [recordId, open]);

  return (
    <Sheet open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <SheetContent
        className="w-full sm:max-w-lg overflow-auto border-l"
        style={{
          backgroundColor: "var(--theme-bg-surface)",
          borderColor: "var(--theme-border)",
        }}
      >
        <SheetHeader>
          <SheetTitle
            className="text-xs font-semibold"
            style={{
              color: "var(--theme-amber)",
              fontFamily: "var(--font-body)",
            }}
          >
            Record Details
          </SheetTitle>
        </SheetHeader>

        {loading ? (
          <RetroLoadingState text="Loading record" />
        ) : !record ? (
          <div className="py-8 text-center">
            <span
              className="text-sm"
              style={{ color: "var(--theme-text-muted)" }}
            >
              Record not found
            </span>
          </div>
        ) : (
          <div className="space-y-4 mt-4">
            <div className="flex items-center gap-2">
              <RetroBadge recordType={record.record_type} />
              {record.status && (
                <span
                  className="text-xs"
                  style={{ color: "var(--theme-text-dim)" }}
                >
                  {record.status}
                </span>
              )}
            </div>

            <p
              className="text-sm font-medium"
              style={{ color: "var(--theme-text)" }}
            >
              {record.display_text}
            </p>

            <div
              className="border-t pt-3 space-y-2"
              style={{ borderColor: "var(--theme-border)" }}
            >
              <DetailRow label="Type" value={record.record_type} />
              <DetailRow label="FHIR" value={record.fhir_resource_type} />
              <DetailRow
                label="Date"
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
              <DetailRow label="Source" value={record.source_format} />
              {record.code_system && (
                <DetailRow label="Code system" value={record.code_system} mono />
              )}
              {record.code_value && (
                <DetailRow label="Code" value={record.code_value} mono />
              )}
              {record.code_display && (
                <DetailRow label="Code display" value={record.code_display} />
              )}
              {record.category && record.category.length > 0 && (
                <DetailRow label="Categories" value={record.category.join(", ")} />
              )}
              <DetailRow
                label="Created"
                value={new Date(record.created_at).toLocaleString()}
              />
            </div>

            {/* FHIR JSON toggle */}
            <div
              className="border-t pt-3"
              style={{ borderColor: "var(--theme-border)" }}
            >
              <button
                onClick={() => setShowFhir(!showFhir)}
                className="text-xs cursor-pointer transition-colors font-medium"
                style={{ color: "var(--theme-amber-dim)" }}
                onMouseEnter={(e) => (e.currentTarget.style.color = "var(--theme-amber)")}
                onMouseLeave={(e) => (e.currentTarget.style.color = "var(--theme-amber-dim)")}
              >
                {showFhir ? "Hide FHIR JSON" : "Show FHIR JSON"}
              </button>
              {showFhir && (
                <pre
                  className="mt-2 p-3 text-xs overflow-auto max-h-80"
                  style={{
                    backgroundColor: "var(--theme-bg-deep)",
                    color: "var(--theme-text-dim)",
                    borderRadius: "4px",
                    border: "1px solid var(--theme-border)",
                  }}
                >
                  {JSON.stringify(record.fhir_resource, null, 2)}
                </pre>
              )}
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

function DetailRow({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1">
      <span
        className="text-xs font-medium shrink-0"
        style={{ color: "var(--theme-text-muted)" }}
      >
        {label}
      </span>
      <span
        className={`text-xs text-right truncate ${mono ? "font-mono" : ""}`}
        style={{ color: "var(--theme-text)" }}
      >
        {value}
      </span>
    </div>
  );
}
