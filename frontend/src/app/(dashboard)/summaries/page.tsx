"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import { api } from "@/lib/api";
import type { PromptResponse, DashboardOverview, RecordListResponse } from "@/types/api";

export default function SummariesPage() {
  const [patientId, setPatientId] = useState<string | null>(null);
  const [summaryType, setSummaryType] = useState("full");
  const [building, setBuilding] = useState(false);
  const [prompt, setPrompt] = useState<PromptResponse | null>(null);
  const [previousPrompts, setPreviousPrompts] = useState<PromptResponse[]>([]);
  const [loadingPrompts, setLoadingPrompts] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    api
      .get<DashboardOverview>("/dashboard/overview")
      .then((data) => {
        if (data.total_patients > 0) {
          // Fetch a record to get the patient_id
          api
            .get<RecordListResponse>("/records?page_size=1")
            .then((records) => {
              if (records.items.length > 0) {
                setPatientId(records.items[0].patient_id);
              }
            })
            .catch(() => {});
        }
      })
      .catch(() => {});

    api
      .get<{ items: PromptResponse[] }>("/summary/prompts")
      .then((data) => setPreviousPrompts(data.items || []))
      .catch(() => setPreviousPrompts([]))
      .finally(() => setLoadingPrompts(false));
  }, []);

  const handleBuildPrompt = async () => {
    if (!patientId) {
      setError("No patient found. Please upload health records first.");
      return;
    }

    setBuilding(true);
    setError(null);
    setPrompt(null);

    try {
      const result = await api.post<PromptResponse>("/summary/build-prompt", {
        patient_id: patientId,
        summary_type: summaryType,
      });
      setPrompt(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to build prompt");
    } finally {
      setBuilding(false);
    }
  };

  const handleCopy = async () => {
    if (!prompt?.copyable_payload) return;
    try {
      await navigator.clipboard.writeText(prompt.copyable_payload);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for non-secure contexts
      const textarea = document.createElement("textarea");
      textarea.value = prompt.copyable_payload;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">AI Summaries</h1>
        <p className="text-muted-foreground">
          Build de-identified prompts for health record summarization
        </p>
      </div>

      <Alert>
        <AlertTitle>AI Disclaimer</AlertTitle>
        <AlertDescription>
          This feature constructs prompts from de-identified health data. No external API calls
          are made by this application. You must copy the prompt and execute it yourself in an
          external tool (e.g., Google AI Studio). Summaries are for personal reference only and
          do not constitute medical advice, diagnoses, or treatment recommendations.
        </AlertDescription>
      </Alert>

      <Card>
        <CardHeader>
          <CardTitle>Build Summary Prompt</CardTitle>
          <CardDescription>
            Select a summary type and generate a de-identified prompt ready to copy
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col sm:flex-row gap-3">
            <select
              className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
              value={summaryType}
              onChange={(e) => setSummaryType(e.target.value)}
            >
              <option value="full">Full Health Summary</option>
              <option value="category">Category Summary</option>
              <option value="date_range">Date Range Summary</option>
              <option value="single_record">Single Record Summary</option>
            </select>
            <Button onClick={handleBuildPrompt} disabled={building || !patientId}>
              {building ? "Building..." : "Build Prompt"}
            </Button>
          </div>
          {!patientId && !building && (
            <p className="text-sm text-muted-foreground">
              No patient data found. Upload health records first to build summaries.
            </p>
          )}
        </CardContent>
      </Card>

      {error && (
        <Alert variant="destructive">
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {prompt && (
        <Card>
          <CardHeader>
            <CardTitle>Generated Prompt</CardTitle>
            <CardDescription>
              {prompt.record_count} records included | Target model: {prompt.target_model} |
              Generated {new Date(prompt.generated_at).toLocaleString()}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {prompt.de_identification_report && (
              <div>
                <p className="text-sm font-medium mb-2">De-identification Report</p>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(prompt.de_identification_report).map(([key, value]) => (
                    <span
                      key={key}
                      className="inline-flex items-center rounded-full bg-blue-100 text-blue-800 px-2.5 py-0.5 text-xs font-medium"
                    >
                      {key.replace(/_/g, " ")}: {value}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <Separator />

            <div>
              <div className="flex items-center justify-between mb-2">
                <p className="text-sm font-medium">Copyable Payload</p>
                <Button size="sm" variant="outline" onClick={handleCopy}>
                  {copied ? "Copied" : "Copy to Clipboard"}
                </Button>
              </div>
              <textarea
                readOnly
                value={prompt.copyable_payload}
                className="w-full h-64 rounded-md border border-input bg-muted p-3 text-xs font-mono resize-y"
              />
            </div>

            <Alert>
              <AlertTitle>Review Before Sending</AlertTitle>
              <AlertDescription>
                Review the prompt above carefully to verify no personal health information (PHI) is
                present before pasting it into any external tool. This application does not make any
                external API calls.
              </AlertDescription>
            </Alert>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Previous Prompts</CardTitle>
          <CardDescription>Previously generated summary prompts</CardDescription>
        </CardHeader>
        <CardContent>
          {loadingPrompts ? (
            <p className="text-sm text-muted-foreground">Loading...</p>
          ) : previousPrompts.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-muted-foreground">No previous prompts found.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {previousPrompts.map((p) => (
                <div
                  key={p.id}
                  className="flex items-center justify-between py-2 border-b last:border-0"
                >
                  <div>
                    <p className="text-sm font-medium">
                      {p.summary_type} summary
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {p.record_count} records | {new Date(p.generated_at).toLocaleDateString()}
                    </p>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {p.target_model}
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
