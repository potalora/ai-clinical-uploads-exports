"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { api } from "@/lib/api";
import type { DedupCandidate } from "@/types/api";

const TYPE_COLORS: Record<string, string> = {
  condition: "bg-amber-100 text-amber-800",
  observation: "bg-teal-100 text-teal-800",
  medication: "bg-violet-100 text-violet-800",
  encounter: "bg-emerald-100 text-emerald-800",
  immunization: "bg-blue-100 text-blue-800",
  procedure: "bg-rose-100 text-rose-800",
  document: "bg-slate-100 text-slate-800",
};

export default function DedupPage() {
  const [candidates, setCandidates] = useState<DedupCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [scanResult, setScanResult] = useState<string | null>(null);

  const fetchCandidates = () => {
    setLoading(true);
    api
      .get<{ items: DedupCandidate[] }>("/dedup/candidates")
      .then((data) => setCandidates((data.items || []).filter((c) => c.status === "pending")))
      .catch(() => setCandidates([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchCandidates();
  }, []);

  const handleScan = async () => {
    setScanning(true);
    setError(null);
    setScanResult(null);

    try {
      const result = await api.post<{ candidates_found: number }>("/dedup/scan");
      setScanResult(`Scan complete. ${result.candidates_found} potential duplicates found.`);
      fetchCandidates();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setScanning(false);
    }
  };

  const handleMerge = async (candidateId: string) => {
    setActionLoading(candidateId);
    try {
      await api.post("/dedup/merge", { candidate_id: candidateId });
      setCandidates((prev) => prev.filter((c) => c.id !== candidateId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Merge failed");
    } finally {
      setActionLoading(null);
    }
  };

  const handleDismiss = async (candidateId: string) => {
    setActionLoading(candidateId);
    try {
      await api.post("/dedup/dismiss", { candidate_id: candidateId });
      setCandidates((prev) => prev.filter((c) => c.id !== candidateId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dismiss failed");
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Deduplication</h1>
        <p className="text-muted-foreground">
          Review and resolve duplicate health records
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Duplicate Scanner</CardTitle>
          <CardDescription>
            Scan your records to find potential duplicates across different data sources
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button onClick={handleScan} disabled={scanning}>
            {scanning ? "Scanning..." : "Scan for Duplicates"}
          </Button>
          {scanResult && (
            <p className="text-sm text-muted-foreground mt-3">{scanResult}</p>
          )}
        </CardContent>
      </Card>

      {error && (
        <Alert variant="destructive">
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Duplicate Candidates</CardTitle>
          <CardDescription>
            {candidates.length} pending candidate{candidates.length !== 1 ? "s" : ""} for review
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center h-32">
              <p className="text-muted-foreground">Loading candidates...</p>
            </div>
          ) : candidates.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-muted-foreground">No duplicate candidates found.</p>
              <p className="text-xs text-muted-foreground mt-1">
                Run the scanner to check for potential duplicates.
              </p>
            </div>
          ) : (
            <div className="space-y-6">
              {candidates.map((candidate) => (
                <div key={candidate.id} className="border rounded-lg p-4 space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">
                        Similarity: {Math.round(candidate.similarity_score * 100)}%
                      </span>
                      <div className="flex gap-1">
                        {Object.entries(candidate.match_reasons)
                          .filter(([, matched]) => matched)
                          .map(([reason]) => (
                            <span
                              key={reason}
                              className="inline-flex items-center rounded-full bg-blue-100 text-blue-800 px-2 py-0.5 text-xs"
                            >
                              {reason}
                            </span>
                          ))}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        onClick={() => handleMerge(candidate.id)}
                        disabled={actionLoading === candidate.id}
                      >
                        {actionLoading === candidate.id ? "..." : "Merge"}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleDismiss(candidate.id)}
                        disabled={actionLoading === candidate.id}
                      >
                        Dismiss
                      </Button>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {candidate.record_a && (
                      <div className="border rounded-md p-3 space-y-2">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-medium text-muted-foreground">Record A</span>
                          <span
                            className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                              TYPE_COLORS[candidate.record_a.record_type] || "bg-gray-100 text-gray-800"
                            }`}
                          >
                            {candidate.record_a.record_type}
                          </span>
                        </div>
                        <p className="text-sm">{candidate.record_a.display_text}</p>
                        <div className="flex items-center gap-3 text-xs text-muted-foreground">
                          <span>{candidate.record_a.source_format}</span>
                          <span>
                            {candidate.record_a.effective_date
                              ? new Date(candidate.record_a.effective_date).toLocaleDateString()
                              : "No date"}
                          </span>
                        </div>
                      </div>
                    )}
                    {candidate.record_b && (
                      <div className="border rounded-md p-3 space-y-2">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-medium text-muted-foreground">Record B</span>
                          <span
                            className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                              TYPE_COLORS[candidate.record_b.record_type] || "bg-gray-100 text-gray-800"
                            }`}
                          >
                            {candidate.record_b.record_type}
                          </span>
                        </div>
                        <p className="text-sm">{candidate.record_b.display_text}</p>
                        <div className="flex items-center gap-3 text-xs text-muted-foreground">
                          <span>{candidate.record_b.source_format}</span>
                          <span>
                            {candidate.record_b.effective_date
                              ? new Date(candidate.record_b.effective_date).toLocaleDateString()
                              : "No date"}
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
