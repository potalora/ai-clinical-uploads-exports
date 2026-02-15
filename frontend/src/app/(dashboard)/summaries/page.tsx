"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type {
  PatientInfo,
  GenerateSummaryResponse,
  PromptResponse,
} from "@/types/api";
import { GlowText } from "@/components/retro/GlowText";
import {
  RetroCard,
  RetroCardHeader,
  RetroCardContent,
} from "@/components/retro/RetroCard";
import { RetroButton } from "@/components/retro/RetroButton";
import { RetroTabs } from "@/components/retro/RetroTabs";
import { RetroLoadingState } from "@/components/retro/RetroLoadingState";

const SUMMARY_TYPES = [
  { key: "full", label: "Full" },
  { key: "category", label: "Category" },
  { key: "date_range", label: "Date range" },
];

const CATEGORIES = [
  { value: "observation", label: "Labs & Vitals" },
  { value: "medication", label: "Medications" },
  { value: "condition", label: "Conditions" },
  { value: "encounter", label: "Encounters" },
  { value: "immunization", label: "Immunizations" },
  { value: "procedure", label: "Procedures" },
];

const OUTPUT_TABS = [
  { key: "nl", label: "Natural language" },
  { key: "json", label: "JSON data" },
];

export default function SummariesPage() {
  // Patient selector
  const [patients, setPatients] = useState<PatientInfo[]>([]);
  const [selectedPatient, setSelectedPatient] = useState("");

  // Config
  const [summaryType, setSummaryType] = useState("full");
  const [category, setCategory] = useState("observation");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [outputFormat, setOutputFormat] = useState("both");
  const [showCustomize, setShowCustomize] = useState(false);
  const [customSystemPrompt, setCustomSystemPrompt] = useState("");

  // Results
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<GenerateSummaryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resultTab, setResultTab] = useState("nl");

  // History
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState<PromptResponse[]>([]);

  // Load patients
  useEffect(() => {
    (async () => {
      try {
        const data = await api.get<{ items: PatientInfo[] }>(
          "/dashboard/patients"
        );
        setPatients(data.items);
        if (data.items.length > 0) setSelectedPatient(data.items[0].id);
      } catch {
        // ignore
      }
    })();
  }, []);

  // Load history
  const loadHistory = useCallback(async () => {
    try {
      const data = await api.get<{ items: PromptResponse[] }>(
        "/summary/prompts"
      );
      setHistory(data.items);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const handleGenerate = async () => {
    if (!selectedPatient) return;
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const body: Record<string, unknown> = {
        patient_id: selectedPatient,
        summary_type: summaryType,
        output_format: outputFormat,
      };
      if (summaryType === "category") body.category = category;
      if (summaryType === "date_range" && dateFrom) body.date_from = dateFrom;
      if (summaryType === "date_range" && dateTo) body.date_to = dateTo;
      if (customSystemPrompt.trim())
        body.custom_system_prompt = customSystemPrompt;

      const resp = await api.post<GenerateSummaryResponse>(
        "/summary/generate",
        body
      );
      setResult(resp);
      loadHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Summary generation failed");
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <GlowText as="h1">AI Health Summary</GlowText>

      {/* Patient Selector */}
      <RetroCard>
        <RetroCardContent>
          <label
            className="text-xs font-medium block mb-2"
            style={{
              color: "var(--theme-text-dim)",
              fontFamily: "var(--font-body)",
            }}
          >
            Select patient
          </label>
          <select
            value={selectedPatient}
            onChange={(e) => setSelectedPatient(e.target.value)}
            className="w-full px-3 py-2 text-sm border"
            style={{
              backgroundColor: "var(--theme-bg-deep)",
              borderColor: "var(--theme-border)",
              color: "var(--theme-text)",
              fontFamily: "var(--font-mono)",
              borderRadius: "4px",
            }}
          >
            {patients.length === 0 && (
              <option value="">No patients found</option>
            )}
            {patients.map((p) => (
              <option key={p.id} value={p.id}>
                {p.fhir_id || p.id.slice(0, 8)} ({p.gender || "unknown"})
              </option>
            ))}
          </select>
        </RetroCardContent>
      </RetroCard>

      {/* Duplicate Warning */}
      {result?.duplicate_warning &&
        result.duplicate_warning.duplicates_excluded > 0 && (
          <RetroCard>
            <RetroCardContent>
              <div className="flex items-start gap-3">
                <span
                  className="text-xs font-bold shrink-0 px-2 py-0.5"
                  style={{
                    backgroundColor: "var(--theme-ochre)",
                    color: "var(--theme-bg-deep)",
                    borderRadius: "4px",
                    fontFamily: "var(--font-body)",
                  }}
                >
                  Dedup
                </span>
                <p
                  className="text-xs leading-relaxed"
                  style={{ color: "var(--theme-text-dim)" }}
                >
                  {result.duplicate_warning.message} Review in Admin &gt; DEDUP
                  tab.
                </p>
              </div>
            </RetroCardContent>
          </RetroCard>
        )}

      {/* Summary Configuration */}
      <RetroCard accentTop>
        <RetroCardHeader>
          <GlowText as="h3" glow={false}>
            Configuration
          </GlowText>
        </RetroCardHeader>
        <RetroCardContent>
          <div className="space-y-4">
            {/* Summary Type */}
            <div>
              <label
                className="text-xs font-medium block mb-2"
                style={{
                  color: "var(--theme-text-dim)",
                  fontFamily: "var(--font-body)",
                }}
              >
                Summary type
              </label>
              <RetroTabs
                tabs={SUMMARY_TYPES}
                active={summaryType}
                onChange={setSummaryType}
              />
            </div>

            {/* Category selector (conditional) */}
            {summaryType === "category" && (
              <div>
                <label
                  className="text-xs font-medium block mb-2"
                  style={{
                    color: "var(--theme-text-dim)",
                    fontFamily: "var(--font-body)",
                  }}
                >
                  Category
                </label>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="w-full px-3 py-2 text-sm border"
                  style={{
                    backgroundColor: "var(--theme-bg-deep)",
                    borderColor: "var(--theme-border)",
                    color: "var(--theme-text)",
                    fontFamily: "var(--font-mono)",
                    borderRadius: "4px",
                  }}
                >
                  {CATEGORIES.map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Date range (conditional) */}
            {summaryType === "date_range" && (
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label
                    className="text-xs font-medium block mb-2"
                    style={{
                      color: "var(--theme-text-dim)",
                      fontFamily: "var(--font-body)",
                    }}
                  >
                    From
                  </label>
                  <input
                    type="date"
                    value={dateFrom}
                    onChange={(e) => setDateFrom(e.target.value)}
                    className="w-full px-3 py-2 text-sm border"
                    style={{
                      backgroundColor: "var(--theme-bg-deep)",
                      borderColor: "var(--theme-border)",
                      color: "var(--theme-text)",
                      fontFamily: "var(--font-mono)",
                      borderRadius: "4px",
                    }}
                  />
                </div>
                <div>
                  <label
                    className="text-xs font-medium block mb-2"
                    style={{
                      color: "var(--theme-text-dim)",
                      fontFamily: "var(--font-body)",
                    }}
                  >
                    To
                  </label>
                  <input
                    type="date"
                    value={dateTo}
                    onChange={(e) => setDateTo(e.target.value)}
                    className="w-full px-3 py-2 text-sm border"
                    style={{
                      backgroundColor: "var(--theme-bg-deep)",
                      borderColor: "var(--theme-border)",
                      color: "var(--theme-text)",
                      fontFamily: "var(--font-mono)",
                      borderRadius: "4px",
                    }}
                  />
                </div>
              </div>
            )}

            {/* Output Format */}
            <div>
              <label
                className="text-xs font-medium block mb-2"
                style={{
                  color: "var(--theme-text-dim)",
                  fontFamily: "var(--font-body)",
                }}
              >
                Output format
              </label>
              <div className="flex gap-4">
                {[
                  { value: "natural_language", label: "Natural Language" },
                  { value: "json", label: "JSON" },
                  { value: "both", label: "Both" },
                ].map((opt) => (
                  <label key={opt.value} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="outputFormat"
                      value={opt.value}
                      checked={outputFormat === opt.value}
                      onChange={(e) => setOutputFormat(e.target.value)}
                      className="accent-amber-500"
                    />
                    <span
                      className="text-xs"
                      style={{
                        color: "var(--theme-text-dim)",
                        fontFamily: "var(--font-body)",
                      }}
                    >
                      {opt.label}
                    </span>
                  </label>
                ))}
              </div>
            </div>

            {/* Customize Prompt (expandable) */}
            <div>
              <button
                onClick={() => setShowCustomize(!showCustomize)}
                className="text-xs cursor-pointer font-medium"
                style={{
                  color: "var(--theme-amber-dim)",
                  fontFamily: "var(--font-body)",
                }}
              >
                {showCustomize ? "Hide prompt options" : "Customize prompt"}
              </button>
              {showCustomize && (
                <div className="mt-2">
                  <textarea
                    value={customSystemPrompt}
                    onChange={(e) => setCustomSystemPrompt(e.target.value)}
                    placeholder="Override system prompt (leave empty for default)..."
                    rows={6}
                    className="w-full px-3 py-2 text-xs border resize-y"
                    style={{
                      backgroundColor: "var(--theme-bg-deep)",
                      borderColor: "var(--theme-border)",
                      color: "var(--theme-text)",
                      fontFamily: "var(--font-mono)",
                      borderRadius: "4px",
                    }}
                  />
                </div>
              )}
            </div>
          </div>
        </RetroCardContent>
      </RetroCard>

      {/* Generate Button */}
      <div className="flex justify-center">
        <RetroButton
          variant="large"
          onClick={handleGenerate}
          disabled={loading || !selectedPatient}
        >
          {loading ? "Generating..." : "Generate summary"}
        </RetroButton>
      </div>

      {/* Loading State */}
      {loading && (
        <RetroLoadingState text="Generating summary" />
      )}

      {/* Error */}
      {error && (
        <RetroCard>
          <RetroCardContent>
            <div className="flex items-start gap-3">
              <span
                className="text-xs font-bold shrink-0 px-2 py-0.5"
                style={{
                  backgroundColor: "var(--theme-terracotta)",
                  color: "var(--theme-text)",
                  borderRadius: "4px",
                  fontFamily: "var(--font-body)",
                }}
              >
                ERROR
              </span>
              <p className="text-xs" style={{ color: "var(--theme-text-dim)" }}>
                {error}
              </p>
            </div>
          </RetroCardContent>
        </RetroCard>
      )}

      {/* Results */}
      {result && (
        <RetroCard accentTop>
          <RetroCardHeader>
            <div className="flex items-center justify-between">
              <GlowText as="h3" glow={false}>
                Summary results
              </GlowText>
              <div className="flex items-center gap-4">
                <span
                  className="text-xs"
                  style={{ color: "var(--theme-text-dim)" }}
                >
                  {result.record_count} records | {result.model_used}
                </span>
              </div>
            </div>
          </RetroCardHeader>
          <RetroCardContent>
            <div className="space-y-4">
              {/* Output tabs */}
              {(result.natural_language || result.json_data) && (
                <RetroTabs
                  tabs={OUTPUT_TABS}
                  active={resultTab}
                  onChange={setResultTab}
                />
              )}

              {/* NL tab */}
              {resultTab === "nl" && result.natural_language && (
                <div
                  className="p-4 text-xs leading-relaxed whitespace-pre-wrap overflow-auto max-h-[600px]"
                  style={{
                    backgroundColor: "var(--theme-bg-deep)",
                    color: "var(--theme-text-dim)",
                    fontFamily: "var(--font-mono)",
                    borderRadius: "4px",
                    border: "1px solid var(--theme-border)",
                  }}
                >
                  {result.natural_language}
                </div>
              )}

              {/* JSON tab */}
              {resultTab === "json" && result.json_data && (
                <div className="relative">
                  <RetroButton
                    variant="ghost"
                    className="absolute top-2 right-2 z-10"
                    onClick={() =>
                      copyToClipboard(
                        JSON.stringify(result.json_data, null, 2)
                      )
                    }
                  >
                    Copy
                  </RetroButton>
                  <pre
                    className="p-4 text-xs overflow-auto max-h-[600px]"
                    style={{
                      backgroundColor: "var(--theme-bg-deep)",
                      color: "var(--theme-sage)",
                      fontFamily: "var(--font-mono)",
                      borderRadius: "4px",
                      border: "1px solid var(--theme-border)",
                    }}
                  >
                    {JSON.stringify(result.json_data, null, 2)}
                  </pre>
                </div>
              )}

              {/* De-identification Report */}
              {result.de_identification_report &&
                Object.keys(result.de_identification_report).length > 0 && (
                  <div
                    className="border-t pt-3 mt-3"
                    style={{ borderColor: "var(--theme-border)" }}
                  >
                    <p
                      className="text-xs font-medium mb-2"
                      style={{
                        color: "var(--theme-text-muted)",
                        fontFamily: "var(--font-body)",
                      }}
                    >
                      De-identification report
                    </p>
                    <div className="grid grid-cols-2 gap-2">
                      {Object.entries(result.de_identification_report).map(
                        ([key, val]) => (
                          <div
                            key={key}
                            className="flex justify-between py-1 px-2"
                            style={{
                              backgroundColor: "var(--theme-bg-deep)",
                              borderRadius: "4px",
                            }}
                          >
                            <span
                              className="text-xs"
                              style={{ color: "var(--theme-text-muted)" }}
                            >
                              {key.replace(/_/g, " ").toUpperCase()}
                            </span>
                            <span
                              className="text-xs font-medium"
                              style={{ color: "var(--theme-amber)" }}
                            >
                              {val}
                            </span>
                          </div>
                        )
                      )}
                    </div>
                  </div>
                )}
            </div>
          </RetroCardContent>
        </RetroCard>
      )}

      {/* AI Disclaimer */}
      <RetroCard>
        <RetroCardContent>
          <div className="flex items-start gap-3">
            <span
              className="text-xs font-bold shrink-0 px-2 py-0.5"
              style={{
                backgroundColor: "var(--theme-terracotta)",
                color: "var(--theme-text)",
                borderRadius: "4px",
                fontFamily: "var(--font-body)",
              }}
            >
              Notice
            </span>
            <p
              className="text-xs leading-relaxed"
              style={{ color: "var(--theme-text-dim)" }}
            >
              AI summaries are for personal reference only and do not constitute
              medical advice, diagnoses, or treatment recommendations. All health
              data is de-identified before being sent to the AI model. Summaries
              are generated by Gemini 3 Flash and may contain inaccuracies.
            </p>
          </div>
        </RetroCardContent>
      </RetroCard>

      {/* History */}
      <div>
        <button
          onClick={() => setShowHistory(!showHistory)}
          className="text-xs cursor-pointer font-medium"
          style={{
            color: "var(--theme-text-dim)",
            fontFamily: "var(--font-body)",
          }}
        >
          {showHistory ? "Hide history" : "Summary history"} ({history.length})
        </button>
        {showHistory && history.length > 0 && (
          <div className="mt-3 space-y-2">
            {history.map((h) => (
              <RetroCard key={h.id}>
                <RetroCardContent>
                  <div className="flex items-center justify-between">
                    <div>
                      <span
                        className="text-xs font-medium"
                        style={{ color: "var(--theme-text)" }}
                      >
                        {h.summary_type} summary
                      </span>
                      <span
                        className="text-xs ml-3"
                        style={{ color: "var(--theme-text-muted)" }}
                      >
                        {h.record_count} records
                      </span>
                    </div>
                    <span
                      className="text-xs"
                      style={{ color: "var(--theme-text-muted)" }}
                    >
                      {h.generated_at
                        ? new Date(h.generated_at).toLocaleDateString()
                        : ""}
                    </span>
                  </div>
                </RetroCardContent>
              </RetroCard>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
