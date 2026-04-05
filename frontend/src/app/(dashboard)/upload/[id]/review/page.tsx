"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ChevronDown, ChevronRight, ArrowLeft, CheckCircle, RotateCcw } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { GlowText } from "@/components/retro/GlowText";
import { RetroCard, RetroCardHeader, RetroCardContent } from "@/components/retro/RetroCard";
import { RetroButton } from "@/components/retro/RetroButton";
import { RetroLoadingState } from "@/components/retro/RetroLoadingState";
import { DedupReviewCard, type ReviewCandidate } from "@/components/retro/DedupReviewCard";

/* ==========================================
   TYPES
   ========================================== */

interface DedupSummary {
  total_candidates: number;
  auto_merged: number;
  needs_review: number;
  dismissed: number;
  by_type: Record<string, number>;
}

interface UploadInfo {
  id: string;
  filename: string;
  uploaded_at: string;
  record_count: number;
  status: string;
  dedup_summary: DedupSummary;
}

interface AutoMergedEntry {
  candidate_id: string;
  primary: {
    id: string;
    display_text: string;
    record_type: string;
    fhir_resource: Record<string, unknown>;
  };
  secondary: {
    id: string;
    display_text: string;
    record_type: string;
    fhir_resource: Record<string, unknown>;
  };
  similarity_score: number;
  llm_classification: string;
  llm_confidence: number;
  llm_explanation: string;
  merged_at: string;
}

interface ReviewResponse {
  upload: UploadInfo;
  auto_merged: AutoMergedEntry[];
  needs_review: Record<string, ReviewCandidate[]>;
}

/* ==========================================
   HELPERS
   ========================================== */

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

function StatusBadge({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    awaiting_review: "#8a7a5a",
    complete: "#4a7a6a",
    processing: "#5a8070",
    failed: "var(--theme-terracotta)",
  };
  const bg = colorMap[status] ?? "#5a8070";
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-md capitalize"
      style={{ backgroundColor: bg, color: "#ffffff", fontFamily: "var(--font-mono)" }}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

/* ==========================================
   AUTO-MERGED SECTION
   ========================================== */

function AutoMergedSection({
  entries,
  onUndo,
}: {
  entries: AutoMergedEntry[];
  onUndo: (candidateId: string) => void;
}) {
  const [open, setOpen] = useState(false);

  if (entries.length === 0) return null;

  return (
    <RetroCard>
      <RetroCardHeader>
        <button
          className="flex items-center gap-2 w-full text-left"
          onClick={() => setOpen((v) => !v)}
        >
          {open ? (
            <ChevronDown className="h-4 w-4 flex-shrink-0" style={{ color: "var(--theme-text-dim)" }} />
          ) : (
            <ChevronRight className="h-4 w-4 flex-shrink-0" style={{ color: "var(--theme-text-dim)" }} />
          )}
          <span
            className="text-sm font-medium"
            style={{ color: "var(--theme-text)", fontFamily: "var(--font-body)" }}
          >
            Auto-Merged
          </span>
          <span
            className="inline-flex items-center px-2 py-0.5 text-xs rounded-full"
            style={{
              backgroundColor: "#4a7a6a",
              color: "#ffffff",
              fontFamily: "var(--font-mono)",
            }}
          >
            {entries.length}
          </span>
          <span
            className="text-xs ml-auto"
            style={{ color: "var(--theme-text-dim)" }}
          >
            {open ? "collapse" : "expand to undo"}
          </span>
        </button>
      </RetroCardHeader>

      {open && (
        <div>
          {entries.map((entry) => (
            <div
              key={entry.candidate_id}
              className="flex items-center gap-3 px-4 py-3 border-b last:border-b-0"
              style={{ borderColor: "var(--theme-border)" }}
            >
              <div className="flex-1 min-w-0">
                <p
                  className="text-sm truncate"
                  style={{ color: "var(--theme-text)", fontFamily: "var(--font-body)" }}
                  title={`${entry.primary.display_text} + ${entry.secondary.display_text}`}
                >
                  {entry.primary.display_text}
                </p>
                <p
                  className="text-xs"
                  style={{ color: "var(--theme-text-dim)", fontFamily: "var(--font-mono)" }}
                >
                  {entry.primary.record_type} &middot; merged {formatDate(entry.merged_at)} &middot; similarity {Math.round(entry.similarity_score * 100)}%
                </p>
              </div>
              <button
                onClick={() => onUndo(entry.candidate_id)}
                className="flex items-center gap-1 text-xs transition-colors duration-150"
                style={{ color: "var(--theme-text-dim)", fontFamily: "var(--font-body)" }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.color = "var(--theme-amber)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.color = "var(--theme-text-dim)";
                }}
              >
                <RotateCcw className="h-3 w-3" />
                Undo
              </button>
            </div>
          ))}
        </div>
      )}
    </RetroCard>
  );
}

/* ==========================================
   ALL RESOLVED STATE
   ========================================== */

function AllResolvedState({ onBack }: { onBack: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-4">
      <CheckCircle className="h-12 w-12" style={{ color: "#4a7a6a" }} />
      <h2
        className="text-xl font-medium"
        style={{ color: "var(--theme-text)", fontFamily: "var(--font-display)" }}
      >
        All candidates resolved
      </h2>
      <p
        className="text-sm"
        style={{ color: "var(--theme-text-dim)", fontFamily: "var(--font-body)" }}
      >
        No remaining deduplication decisions for this upload.
      </p>
      <RetroButton variant="ghost" onClick={onBack}>
        <ArrowLeft className="h-4 w-4 mr-2" />
        Back to Uploads
      </RetroButton>
    </div>
  );
}

/* ==========================================
   MAIN PAGE
   ========================================== */

export default function ReviewPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const uploadId = params.id;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<ReviewResponse | null>(null);

  // Track resolved candidate IDs so we can hide them optimistically
  const [resolved, setResolved] = useState<Set<string>>(new Set());
  const [resolving, setResolving] = useState<Set<string>>(new Set());

  // Bulk selection
  const [selected, setSelected] = useState<Set<string>>(new Set());

  /* ---- Data fetching ---- */
  const fetchReview = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.get<ReviewResponse>(`/upload/${uploadId}/review`);
      setData(result);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Failed to load review data.");
      }
    } finally {
      setLoading(false);
    }
  }, [uploadId]);

  useEffect(() => {
    fetchReview();
  }, [fetchReview]);

  /* ---- Resolve handler ---- */
  const handleResolve = useCallback(
    async (candidateId: string, action: "accept" | "decline") => {
      if (resolving.has(candidateId) || resolved.has(candidateId)) return;

      setResolving((prev) => new Set(prev).add(candidateId));
      try {
        await api.post(`/upload/${uploadId}/review/resolve`, {
          candidate_id: candidateId,
          action,
        });
        setResolved((prev) => {
          const next = new Set(prev);
          next.add(candidateId);
          return next;
        });
        setSelected((prev) => {
          const next = new Set(prev);
          next.delete(candidateId);
          return next;
        });
      } catch (err) {
        console.error("Failed to resolve candidate:", err);
      } finally {
        setResolving((prev) => {
          const next = new Set(prev);
          next.delete(candidateId);
          return next;
        });
      }
    },
    [uploadId, resolved, resolving]
  );

  /* ---- Undo merge handler ---- */
  const handleUndoMerge = useCallback(
    async (candidateId: string) => {
      try {
        await api.post(`/upload/${uploadId}/review/undo-merge`, {
          candidate_id: candidateId,
        });
        // Refresh data after undo
        await fetchReview();
      } catch (err) {
        console.error("Failed to undo merge:", err);
      }
    },
    [uploadId, fetchReview]
  );

  /* ---- Toggle select ---- */
  const handleToggleSelect = useCallback((candidateId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(candidateId)) {
        next.delete(candidateId);
      } else {
        next.add(candidateId);
      }
      return next;
    });
  }, []);

  /* ---- Bulk resolve ---- */
  const handleBulkResolve = useCallback(
    async (action: "accept" | "decline") => {
      const ids = Array.from(selected).filter(
        (id) => !resolved.has(id) && !resolving.has(id)
      );
      for (const id of ids) {
        await handleResolve(id, action);
      }
    },
    [selected, resolved, resolving, handleResolve]
  );

  /* ---- Derived state ---- */
  const needsReviewByType = data?.needs_review ?? {};
  const totalNeedsReview = Object.values(needsReviewByType).reduce(
    (sum, arr) => sum + arr.filter((c) => !resolved.has(c.candidate_id)).length,
    0
  );
  const resolvedCount = resolved.size;
  const totalCandidates =
    (data?.upload.dedup_summary.needs_review ?? 0);
  const allResolved = totalNeedsReview === 0 && !loading && data !== null;

  /* ---- Render ---- */
  if (loading) {
    return (
      <div className="space-y-6">
        <RetroLoadingState text="Loading review data" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-4">
        <RetroButton variant="ghost" onClick={() => router.push("/upload")}>
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back to Uploads
        </RetroButton>
        <RetroCard>
          <RetroCardContent>
            <p className="text-sm" style={{ color: "var(--theme-terracotta)" }}>
              {error}
            </p>
          </RetroCardContent>
        </RetroCard>
      </div>
    );
  }

  if (!data) return null;

  if (allResolved) {
    return <AllResolvedState onBack={() => router.push("/upload")} />;
  }

  const { upload, auto_merged } = data;

  return (
    <div className="space-y-6 pb-24">
      {/* Back nav */}
      <button
        onClick={() => router.push("/upload")}
        className="flex items-center gap-2 text-xs transition-colors duration-150"
        style={{ color: "var(--theme-text-dim)", fontFamily: "var(--font-body)" }}
        onMouseEnter={(e) => { e.currentTarget.style.color = "var(--theme-amber)"; }}
        onMouseLeave={(e) => { e.currentTarget.style.color = "var(--theme-text-dim)"; }}
      >
        <ArrowLeft className="h-3 w-3" />
        Back to Uploads
      </button>

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <GlowText as="h1">
            Dedup Review
          </GlowText>
          <p
            className="mt-1 text-sm"
            style={{ color: "var(--theme-text-dim)", fontFamily: "var(--font-body)" }}
          >
            {upload.filename}
          </p>
        </div>
        <StatusBadge status={upload.status} />
      </div>

      {/* Upload metadata */}
      <RetroCard>
        <RetroCardContent className="py-3">
          <div className="flex items-center gap-6 flex-wrap">
            <div>
              <p className="text-xs" style={{ color: "var(--theme-text-dim)" }}>
                Uploaded
              </p>
              <p
                className="text-sm font-medium"
                style={{ color: "var(--theme-text)", fontFamily: "var(--font-mono)" }}
              >
                {formatDate(upload.uploaded_at)}
              </p>
            </div>
            <div>
              <p className="text-xs" style={{ color: "var(--theme-text-dim)" }}>
                Records
              </p>
              <p
                className="text-sm font-medium"
                style={{ color: "var(--theme-text)", fontFamily: "var(--font-mono)" }}
              >
                {upload.record_count.toLocaleString()}
              </p>
            </div>
            <div>
              <p className="text-xs" style={{ color: "var(--theme-text-dim)" }}>
                Total Candidates
              </p>
              <p
                className="text-sm font-medium"
                style={{ color: "var(--theme-text)", fontFamily: "var(--font-mono)" }}
              >
                {upload.dedup_summary.total_candidates}
              </p>
            </div>
            <div>
              <p className="text-xs" style={{ color: "var(--theme-text-dim)" }}>
                Auto-Merged
              </p>
              <p
                className="text-sm font-medium"
                style={{ color: "#4a7a6a", fontFamily: "var(--font-mono)" }}
              >
                {upload.dedup_summary.auto_merged}
              </p>
            </div>
            <div>
              <p className="text-xs" style={{ color: "var(--theme-text-dim)" }}>
                Needs Review
              </p>
              <p
                className="text-sm font-medium"
                style={{ color: "#8a7a5a", fontFamily: "var(--font-mono)" }}
              >
                {upload.dedup_summary.needs_review}
              </p>
            </div>
          </div>
        </RetroCardContent>
      </RetroCard>

      {/* Summary bar */}
      <div
        className="flex items-center gap-4 px-4 py-2 rounded-md text-xs"
        style={{
          backgroundColor: "var(--theme-bg-card)",
          borderColor: "var(--theme-border)",
          border: "1px solid",
          fontFamily: "var(--font-mono)",
          color: "var(--theme-text-dim)",
        }}
      >
        <span>
          <span style={{ color: "#4a7a6a" }}>{upload.dedup_summary.auto_merged}</span>
          {" "}auto-merged
        </span>
        <span style={{ color: "var(--theme-border)" }}>/</span>
        <span>
          <span style={{ color: "#8a7a5a" }}>{totalNeedsReview}</span>
          {" "}remaining
        </span>
        <span style={{ color: "var(--theme-border)" }}>/</span>
        <span>
          <span style={{ color: "var(--theme-text)" }}>{resolvedCount}</span>
          {" "}resolved this session
        </span>
      </div>

      {/* Auto-merged section */}
      <AutoMergedSection entries={auto_merged} onUndo={handleUndoMerge} />

      {/* Needs review section */}
      {Object.keys(needsReviewByType).length > 0 && (
        <div className="space-y-4">
          <h2
            className="text-sm font-medium"
            style={{ color: "var(--theme-text-dim)", fontFamily: "var(--font-body)" }}
          >
            Needs Review
          </h2>
          {Object.entries(needsReviewByType).map(([recordType, candidates]) => {
            const visible = candidates.filter((c) => !resolved.has(c.candidate_id));
            if (visible.length === 0) return null;
            return (
              <DedupReviewCard
                key={recordType}
                recordType={recordType}
                candidates={visible}
                onResolve={handleResolve}
                selected={selected}
                onToggleSelect={handleToggleSelect}
              />
            );
          })}
        </div>
      )}

      {/* Sticky bulk action bar */}
      {selected.size > 0 && (
        <div
          className="fixed bottom-0 left-0 right-0 z-50 flex items-center justify-between gap-4 px-6 py-4 border-t"
          style={{
            backgroundColor: "var(--theme-bg-card)",
            borderColor: "var(--theme-border)",
          }}
        >
          <span
            className="text-sm"
            style={{ color: "var(--theme-text-dim)", fontFamily: "var(--font-body)" }}
          >
            <span style={{ color: "var(--theme-text)", fontFamily: "var(--font-mono)" }}>
              {selected.size}
            </span>
            {" "}selected &middot;{" "}
            <span style={{ color: "var(--theme-text)" }}>
              {resolvedCount}/{totalCandidates}
            </span>
            {" "}resolved
          </span>
          <div className="flex items-center gap-3">
            <RetroButton
              variant="ghost"
              onClick={() => setSelected(new Set())}
              className="text-xs"
            >
              Clear
            </RetroButton>
            <RetroButton
              variant="ghost"
              onClick={() => handleBulkResolve("decline")}
              className="text-xs"
            >
              Decline Selected ({selected.size})
            </RetroButton>
            <RetroButton
              variant="primary"
              onClick={() => handleBulkResolve("accept")}
              className="text-xs"
            >
              Accept Selected ({selected.size})
            </RetroButton>
          </div>
        </div>
      )}
    </div>
  );
}
