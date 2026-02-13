"use client";

import { useCallback, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useDropzone } from "react-dropzone";
import { api } from "@/lib/api";
import { useAuthStore } from "@/stores/useAuthStore";
import type {
  RecordListResponse,
  HealthRecord,
  LabItem,
  UploadResponse,
  DedupCandidate,
  UserResponse,
  DashboardOverview,
  UnstructuredUploadResponse,
  ExtractionResult,
  ExtractedEntity,
  PatientInfo,
} from "@/types/api";
import { RECORD_TYPE_COLORS, RECORD_TYPE_LABELS, DEFAULT_RECORD_COLOR } from "@/lib/constants";
import { GlowText } from "@/components/retro/GlowText";
import { RetroTabs } from "@/components/retro/RetroTabs";
import { RetroCard, RetroCardHeader, RetroCardContent } from "@/components/retro/RetroCard";
import { RetroButton } from "@/components/retro/RetroButton";
import { RetroInput } from "@/components/retro/RetroInput";
import { RetroLoadingState } from "@/components/retro/RetroLoadingState";
import { RetroBadge } from "@/components/retro/RetroBadge";
import {
  RetroTable,
  RetroTableHeader,
  RetroTableHead,
  RetroTableBody,
  RetroTableRow,
  RetroTableCell,
} from "@/components/retro/RetroTable";
import { RecordDetailSheet } from "@/components/retro/RecordDetailSheet";

const TABS = [
  { key: "all", label: "ALL" },
  { key: "labs", label: "LABS" },
  { key: "meds", label: "MEDS" },
  { key: "cond", label: "COND" },
  { key: "enc", label: "ENC" },
  { key: "immun", label: "IMMUN" },
  { key: "img", label: "IMG" },
  { key: "sep", label: "|", separator: true },
  { key: "upload", label: "UPLOAD" },
  { key: "dedup", label: "DEDUP" },
  { key: "sys", label: "SYS" },
];

export default function AdminPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const initialTab = searchParams.get("tab") || "all";
  const [activeTab, setActiveTab] = useState(initialTab);

  const handleTabChange = (key: string) => {
    setActiveTab(key);
    router.replace(`/admin?tab=${key}`, { scroll: false });
  };

  return (
    <div className="space-y-6">
      <GlowText as="h1">ADMIN CONSOLE</GlowText>
      <RetroTabs tabs={TABS} active={activeTab} onChange={handleTabChange} />
      <div className="mt-4">
        {activeTab === "all" && <AllRecordsTab />}
        {activeTab === "labs" && <LabsTab />}
        {activeTab === "meds" && <RecordTypeTab recordType="medication" label="MEDICATIONS" />}
        {activeTab === "cond" && <RecordTypeTab recordType="condition" label="CONDITIONS" />}
        {activeTab === "enc" && <RecordTypeTab recordType="encounter" label="ENCOUNTERS" />}
        {activeTab === "immun" && <RecordTypeTab recordType="immunization" label="IMMUNIZATIONS" />}
        {activeTab === "img" && <RecordTypeTab recordType="imaging" label="IMAGING" />}
        {activeTab === "upload" && <UploadTab />}
        {activeTab === "dedup" && <DedupTab />}
        {activeTab === "sys" && <SystemTab />}
      </div>
    </div>
  );
}

/* ==========================================
   ALL RECORDS TAB
   ========================================== */

function AllRecordsTab() {
  const [data, setData] = useState<RecordListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [recordType, setRecordType] = useState("");
  const [selectedRecord, setSelectedRecord] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    let endpoint = `/records?page=${page}&page_size=20`;
    if (recordType) endpoint += `&record_type=${recordType}`;
    if (search) endpoint += `&search=${encodeURIComponent(search)}`;

    api
      .get<RecordListResponse>(endpoint)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [page, recordType, search]);

  const totalPages = data ? Math.ceil(data.total / data.page_size) : 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="flex flex-1 gap-2">
          <RetroInput
            placeholder="Search records..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") { setSearch(searchInput); setPage(1); }
            }}
          />
          <RetroButton
            variant="ghost"
            onClick={() => { setSearch(searchInput); setPage(1); }}
          >
            SEARCH
          </RetroButton>
        </div>
        <select
          className="h-9 px-3 text-xs border"
          style={{
            backgroundColor: "var(--retro-bg-card)",
            color: "var(--retro-text)",
            borderColor: "var(--retro-border)",
            borderRadius: "2px",
          }}
          value={recordType}
          onChange={(e) => { setRecordType(e.target.value); setPage(1); }}
        >
          <option value="">ALL TYPES</option>
          {Object.entries(RECORD_TYPE_LABELS).map(([val, label]) => (
            <option key={val} value={val}>{label.toUpperCase()}</option>
          ))}
        </select>
      </div>

      {loading ? (
        <RetroLoadingState text="LOADING RECORDS" />
      ) : !data || data.items.length === 0 ? (
        <div className="py-12 text-center">
          <p
            className="text-xs tracking-wider"
            style={{ color: "var(--retro-text-muted)" }}
          >
            NO RECORDS FOUND
          </p>
          {(search || recordType) && (
            <button
              onClick={() => { setSearch(""); setSearchInput(""); setRecordType(""); setPage(1); }}
              className="mt-2 text-xs uppercase tracking-wider cursor-pointer"
              style={{ color: "var(--retro-amber-dim)" }}
            >
              CLEAR FILTERS
            </button>
          )}
        </div>
      ) : (
        <>
          <RetroTable>
            <RetroTableHeader>
              <RetroTableHead>TYPE</RetroTableHead>
              <RetroTableHead>DESCRIPTION</RetroTableHead>
              <RetroTableHead>DATE</RetroTableHead>
              <RetroTableHead>SOURCE</RetroTableHead>
            </RetroTableHeader>
            <RetroTableBody>
              {data.items.map((record) => (
                <RetroTableRow
                  key={record.id}
                  onClick={() => setSelectedRecord(record.id)}
                >
                  <RetroTableCell>
                    <RetroBadge recordType={record.record_type} short />
                  </RetroTableCell>
                  <RetroTableCell className="max-w-md truncate">
                    {record.display_text}
                  </RetroTableCell>
                  <RetroTableCell>
                    <span style={{ color: "var(--retro-text-dim)" }}>
                      {record.effective_date
                        ? new Date(record.effective_date).toLocaleDateString()
                        : "--"}
                    </span>
                  </RetroTableCell>
                  <RetroTableCell>
                    <span
                      className="text-xs"
                      style={{ color: "var(--retro-text-muted)" }}
                    >
                      {record.source_format}
                    </span>
                  </RetroTableCell>
                </RetroTableRow>
              ))}
            </RetroTableBody>
          </RetroTable>

          <div className="flex items-center justify-between">
            <span
              className="text-xs"
              style={{ color: "var(--retro-text-dim)" }}
            >
              {(data.page - 1) * data.page_size + 1}–
              {Math.min(data.page * data.page_size, data.total)} of {data.total}
            </span>
            <div className="flex gap-2">
              <RetroButton
                variant="ghost"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                PREV
              </RetroButton>
              <RetroButton
                variant="ghost"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                NEXT
              </RetroButton>
            </div>
          </div>
        </>
      )}

      <RecordDetailSheet
        recordId={selectedRecord}
        open={!!selectedRecord}
        onClose={() => setSelectedRecord(null)}
      />
    </div>
  );
}

/* ==========================================
   LABS TAB
   ========================================== */

function interpretationStyle(interpretation: string): { color: string } {
  const code = interpretation?.toUpperCase();
  if (code === "H" || code === "HH") return { color: "var(--retro-terracotta)" };
  if (code === "L" || code === "LL") return { color: "#5a7a8c" };
  if (code === "A" || code === "AA") return { color: "var(--retro-ochre)" };
  return { color: "var(--retro-text-dim)" };
}

function interpretationLabel(interpretation: string): string {
  const code = interpretation?.toUpperCase();
  if (code === "H") return "HIGH";
  if (code === "HH") return "CRIT HIGH";
  if (code === "L") return "LOW";
  if (code === "LL") return "CRIT LOW";
  if (code === "A") return "ABNORMAL";
  if (code === "AA") return "CRIT ABNORM";
  if (code === "N") return "NORMAL";
  return interpretation || "--";
}

function LabsTab() {
  const [labs, setLabs] = useState<LabItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<{ items: LabItem[] }>("/dashboard/labs")
      .then((data) => setLabs(data.items || []))
      .catch(() => setLabs([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <RetroLoadingState text="LOADING LAB RESULTS" />;

  if (labs.length === 0) {
    return (
      <div className="py-12 text-center">
        <p
          className="text-xs tracking-wider"
          style={{ color: "var(--retro-text-muted)" }}
        >
          NO LAB RESULTS FOUND
        </p>
      </div>
    );
  }

  return (
    <RetroTable>
      <RetroTableHeader>
        <RetroTableHead>TEST</RetroTableHead>
        <RetroTableHead>VALUE</RetroTableHead>
        <RetroTableHead>REF RANGE</RetroTableHead>
        <RetroTableHead>INTERP</RetroTableHead>
        <RetroTableHead>DATE</RetroTableHead>
      </RetroTableHeader>
      <RetroTableBody>
        {labs.map((lab) => (
          <RetroTableRow key={lab.id}>
            <RetroTableCell>
              <div>
                <p className="text-sm font-medium">{lab.display_text}</p>
                {lab.code_display && lab.code_display !== lab.display_text && (
                  <p className="text-xs" style={{ color: "var(--retro-text-muted)" }}>
                    {lab.code_display}
                  </p>
                )}
              </div>
            </RetroTableCell>
            <RetroTableCell>
              <span className="font-mono text-sm">
                {lab.value !== null && lab.value !== undefined ? String(lab.value) : "--"}
                {lab.unit && (
                  <span className="ml-1" style={{ color: "var(--retro-text-muted)" }}>
                    {lab.unit}
                  </span>
                )}
              </span>
            </RetroTableCell>
            <RetroTableCell>
              <span style={{ color: "var(--retro-text-dim)" }}>
                {lab.reference_low !== null && lab.reference_high !== null
                  ? `${lab.reference_low}–${lab.reference_high}`
                  : lab.reference_low !== null
                  ? `>= ${lab.reference_low}`
                  : lab.reference_high !== null
                  ? `<= ${lab.reference_high}`
                  : "--"}
              </span>
            </RetroTableCell>
            <RetroTableCell>
              <span
                className="text-xs font-medium uppercase tracking-wider"
                style={interpretationStyle(lab.interpretation)}
              >
                {interpretationLabel(lab.interpretation)}
              </span>
            </RetroTableCell>
            <RetroTableCell>
              <span style={{ color: "var(--retro-text-dim)" }}>
                {lab.effective_date
                  ? new Date(lab.effective_date).toLocaleDateString()
                  : "--"}
              </span>
            </RetroTableCell>
          </RetroTableRow>
        ))}
      </RetroTableBody>
    </RetroTable>
  );
}

/* ==========================================
   GENERIC RECORD TYPE TAB
   ========================================== */

function statusColor(status: string | null): string {
  if (!status) return "var(--retro-text-dim)";
  const s = status.toLowerCase();
  if (s === "active" || s === "in-progress") return "var(--retro-ochre)";
  if (s === "completed" || s === "resolved" || s === "finished") return "var(--retro-sage)";
  if (s === "stopped" || s === "cancelled" || s === "not-done") return "var(--retro-terracotta)";
  return "var(--retro-text-dim)";
}

function RecordTypeTab({ recordType, label }: { recordType: string; label: string }) {
  const [records, setRecords] = useState<HealthRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedRecord, setSelectedRecord] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<RecordListResponse>(`/records?record_type=${recordType}&page_size=100`)
      .then((data) => setRecords(data.items || []))
      .catch(() => setRecords([]))
      .finally(() => setLoading(false));
  }, [recordType]);

  if (loading) return <RetroLoadingState text={`LOADING ${label}`} />;

  if (records.length === 0) {
    return (
      <div className="py-12 text-center">
        <p
          className="text-xs tracking-wider"
          style={{ color: "var(--retro-text-muted)" }}
        >
          NO {label} FOUND
        </p>
      </div>
    );
  }

  return (
    <>
      <RetroTable>
        <RetroTableHeader>
          <RetroTableHead>NAME</RetroTableHead>
          <RetroTableHead>STATUS</RetroTableHead>
          <RetroTableHead>DATE</RetroTableHead>
        </RetroTableHeader>
        <RetroTableBody>
          {records.map((record) => (
            <RetroTableRow
              key={record.id}
              onClick={() => setSelectedRecord(record.id)}
            >
              <RetroTableCell className="max-w-lg truncate">
                {record.display_text}
              </RetroTableCell>
              <RetroTableCell>
                {record.status ? (
                  <span
                    className="text-xs font-medium uppercase tracking-wider"
                    style={{ color: statusColor(record.status) }}
                  >
                    {record.status}
                  </span>
                ) : (
                  <span style={{ color: "var(--retro-text-muted)" }}>--</span>
                )}
              </RetroTableCell>
              <RetroTableCell>
                <span style={{ color: "var(--retro-text-dim)" }}>
                  {record.effective_date
                    ? new Date(record.effective_date).toLocaleDateString()
                    : "--"}
                </span>
              </RetroTableCell>
            </RetroTableRow>
          ))}
        </RetroTableBody>
      </RetroTable>

      <RecordDetailSheet
        recordId={selectedRecord}
        open={!!selectedRecord}
        onClose={() => setSelectedRecord(null)}
      />
    </>
  );
}

/* ==========================================
   UPLOAD TAB
   ========================================== */

function UploadTab() {
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    if (acceptedFiles.length > 0) {
      setSelectedFile(acceptedFiles[0]);
      setResult(null);
      setError(null);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/json": [".json"],
      "application/zip": [".zip"],
      "application/x-zip-compressed": [".zip"],
    },
    maxFiles: 1,
    multiple: false,
  });

  const handleUpload = async () => {
    if (!selectedFile) return;
    setUploading(true);
    setError(null);
    setResult(null);

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      const response = await api.postForm<UploadResponse>("/upload", formData);
      setResult(response);
      setSelectedFile(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Drop zone */}
      <div
        {...getRootProps()}
        className="border-2 border-dashed p-12 text-center cursor-pointer transition-colors"
        style={{
          borderColor: isDragActive ? "var(--retro-amber)" : "var(--retro-border)",
          backgroundColor: isDragActive ? "var(--retro-bg-card-hover)" : "var(--retro-bg-card)",
          borderRadius: "2px",
        }}
      >
        <input {...getInputProps()} />
        {isDragActive ? (
          <p
            className="text-sm tracking-wider"
            style={{ color: "var(--retro-amber)", fontFamily: "var(--font-display)" }}
          >
            DROP FILES TO INITIATE DATA TRANSFER
          </p>
        ) : (
          <div className="space-y-2">
            <p
              className="text-sm tracking-wider"
              style={{ color: "var(--retro-text-dim)", fontFamily: "var(--font-display)" }}
            >
              DROP FILES TO INITIATE DATA TRANSFER
            </p>
            <p className="text-xs" style={{ color: "var(--retro-text-muted)" }}>
              JSON or ZIP files up to 500MB
            </p>
          </div>
        )}
      </div>

      {/* Selected file */}
      {selectedFile && (
        <RetroCard>
          <RetroCardContent>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium" style={{ color: "var(--retro-text)" }}>
                  {selectedFile.name}
                </p>
                <p className="text-xs" style={{ color: "var(--retro-text-muted)" }}>
                  {(selectedFile.size / 1024).toFixed(1)} KB
                </p>
              </div>
              <div className="flex gap-2">
                <RetroButton variant="ghost" onClick={() => setSelectedFile(null)}>
                  REMOVE
                </RetroButton>
                <RetroButton onClick={handleUpload} disabled={uploading}>
                  {uploading ? "UPLOADING..." : "UPLOAD"}
                </RetroButton>
              </div>
            </div>
          </RetroCardContent>
        </RetroCard>
      )}

      {/* Error */}
      {error && (
        <RetroCard>
          <RetroCardContent>
            <div className="flex items-start gap-3">
              <span
                className="text-xs font-bold shrink-0 px-2 py-0.5"
                style={{
                  backgroundColor: "var(--retro-terracotta)",
                  color: "var(--retro-text)",
                  borderRadius: "2px",
                }}
              >
                ERROR
              </span>
              <p className="text-xs" style={{ color: "var(--retro-text-dim)" }}>{error}</p>
            </div>
          </RetroCardContent>
        </RetroCard>
      )}

      {/* Result */}
      {result && (
        <RetroCard accentTop>
          <RetroCardHeader>
            <GlowText as="h4" glow={false}>UPLOAD COMPLETE</GlowText>
          </RetroCardHeader>
          <RetroCardContent>
            <div className="space-y-2">
              <div className="flex justify-between py-1">
                <span className="text-xs" style={{ color: "var(--retro-text-dim)" }}>STATUS</span>
                <span className="text-xs font-medium" style={{ color: "var(--retro-sage)" }}>
                  {result.status}
                </span>
              </div>
              <div className="flex justify-between py-1">
                <span className="text-xs" style={{ color: "var(--retro-text-dim)" }}>
                  RECORDS INSERTED
                </span>
                <span className="text-xs font-medium" style={{ color: "var(--retro-text)" }}>
                  {result.records_inserted}
                </span>
              </div>
              {Array.isArray(result.errors) && result.errors.length > 0 && (
                <div className="pt-2">
                  <p className="text-xs font-medium mb-2" style={{ color: "var(--retro-terracotta)" }}>
                    ERRORS ({result.errors.length})
                  </p>
                  <div className="max-h-48 overflow-auto space-y-1">
                    {result.errors.map((err, i) => (
                      <p
                        key={i}
                        className="text-xs font-mono p-2"
                        style={{
                          backgroundColor: "var(--retro-bg-deep)",
                          color: "var(--retro-text-dim)",
                          borderRadius: "2px",
                        }}
                      >
                        {typeof err === "string" ? err : JSON.stringify(err)}
                      </p>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </RetroCardContent>
        </RetroCard>
      )}

      {/* Unstructured Upload Section */}
      <UnstructuredUploadSection />
    </div>
  );
}

/* ==========================================
   UNSTRUCTURED UPLOAD SECTION
   ========================================== */

function UnstructuredUploadSection() {
  const [unstrFile, setUnstrFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadId, setUploadId] = useState<string | null>(null);
  const [extraction, setExtraction] = useState<ExtractionResult | null>(null);
  const [pollInterval, setPollInterval] = useState<ReturnType<typeof setInterval> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedEntities, setSelectedEntities] = useState<Set<number>>(new Set());
  const [patients, setPatients] = useState<PatientInfo[]>([]);
  const [selectedPatient, setSelectedPatient] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [confirmResult, setConfirmResult] = useState<{records_created: number} | null>(null);

  const onDropUnstr = useCallback((acceptedFiles: File[]) => {
    if (acceptedFiles.length > 0) {
      setUnstrFile(acceptedFiles[0]);
      setExtraction(null);
      setUploadId(null);
      setError(null);
      setConfirmResult(null);
    }
  }, []);

  const { getRootProps: getUnstrRootProps, getInputProps: getUnstrInputProps, isDragActive: isUnstrDragActive } = useDropzone({
    onDrop: onDropUnstr,
    accept: {
      "application/pdf": [".pdf"],
      "application/rtf": [".rtf"],
      "text/rtf": [".rtf"],
      "image/tiff": [".tif", ".tiff"],
    },
    maxFiles: 1,
    multiple: false,
  });

  // Load patients for selector
  useEffect(() => {
    (async () => {
      try {
        const data = await api.get<{ items: PatientInfo[] }>("/dashboard/patients");
        setPatients(data.items);
        if (data.items.length > 0) setSelectedPatient(data.items[0].id);
      } catch { /* ignore */ }
    })();
  }, []);

  // Poll for extraction results
  useEffect(() => {
    if (!uploadId) return;

    const poll = setInterval(async () => {
      try {
        const data = await api.get<ExtractionResult>(`/upload/${uploadId}/extraction`);
        setExtraction(data);

        if (data.status === "awaiting_confirmation" || data.status === "completed" || data.status === "failed") {
          clearInterval(poll);
          setPollInterval(null);
          if (data.entities.length > 0) {
            setSelectedEntities(new Set(data.entities.map((_, i) => i)));
          }
          if (data.error) {
            setError(data.error);
          }
        }
      } catch {
        clearInterval(poll);
        setPollInterval(null);
      }
    }, 2000);

    setPollInterval(poll);
    return () => clearInterval(poll);
  }, [uploadId]);

  const handleUnstrUpload = async () => {
    if (!unstrFile) return;
    setUploading(true);
    setError(null);
    setExtraction(null);
    setConfirmResult(null);

    try {
      const formData = new FormData();
      formData.append("file", unstrFile);
      const resp = await api.postForm<UnstructuredUploadResponse>("/upload/unstructured", formData);
      setUploadId(resp.upload_id);
      setUnstrFile(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const toggleEntity = (index: number) => {
    const next = new Set(selectedEntities);
    if (next.has(index)) next.delete(index);
    else next.add(index);
    setSelectedEntities(next);
  };

  const handleConfirm = async () => {
    if (!extraction || !selectedPatient) return;
    setConfirming(true);
    setError(null);

    try {
      const confirmed = extraction.entities
        .filter((_, i) => selectedEntities.has(i))
        .map(e => ({
          entity_class: e.entity_class,
          text: e.text,
          attributes: e.attributes,
          start_pos: e.start_pos,
          end_pos: e.end_pos,
          confidence: e.confidence,
        }));

      const resp = await api.post<{records_created: number}>(`/upload/${uploadId}/confirm-extraction`, {
        confirmed_entities: confirmed,
        patient_id: selectedPatient,
      });
      setConfirmResult(resp);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Confirmation failed");
    } finally {
      setConfirming(false);
    }
  };

  const ENTITY_COLORS: Record<string, string> = {
    medication: "var(--retro-amber)",
    condition: "var(--retro-ochre)",
    lab_result: "var(--retro-sage)",
    vital: "var(--retro-sage)",
    procedure: "#5a7a8c",
    allergy: "var(--retro-terracotta)",
    provider: "var(--retro-text-dim)",
    dosage: "var(--retro-text-muted)",
    route: "var(--retro-text-muted)",
    frequency: "var(--retro-text-muted)",
    duration: "var(--retro-text-muted)",
  };

  return (
    <div className="space-y-4 mt-8">
      <div className="flex items-center gap-2">
        <div className="flex-1 h-px" style={{ backgroundColor: "var(--retro-border)" }} />
        <span className="text-xs tracking-widest" style={{ color: "var(--retro-amber-dim)", fontFamily: "var(--font-display)" }}>
          UNSTRUCTURED DATA UPLOAD
        </span>
        <div className="flex-1 h-px" style={{ backgroundColor: "var(--retro-border)" }} />
      </div>

      {/* Dropzone for unstructured files */}
      <div
        {...getUnstrRootProps()}
        className="border-2 border-dashed p-8 text-center cursor-pointer transition-colors"
        style={{
          borderColor: isUnstrDragActive ? "var(--retro-amber)" : "var(--retro-border)",
          backgroundColor: isUnstrDragActive ? "var(--retro-bg-card-hover)" : "var(--retro-bg-card)",
          borderRadius: "2px",
        }}
      >
        <input {...getUnstrInputProps()} />
        <div className="space-y-2">
          <p className="text-sm tracking-wider" style={{ color: "var(--retro-text-dim)", fontFamily: "var(--font-display)" }}>
            DROP PDF, RTF, OR TIFF FOR AI EXTRACTION
          </p>
          <p className="text-xs" style={{ color: "var(--retro-text-muted)" }}>
            Clinical notes, scanned documents, reports
          </p>
        </div>
      </div>

      {/* Selected unstructured file */}
      {unstrFile && (
        <RetroCard>
          <RetroCardContent>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium" style={{ color: "var(--retro-text)" }}>{unstrFile.name}</p>
                <p className="text-xs" style={{ color: "var(--retro-text-muted)" }}>{(unstrFile.size / 1024).toFixed(1)} KB</p>
              </div>
              <div className="flex gap-2">
                <RetroButton variant="ghost" onClick={() => setUnstrFile(null)}>REMOVE</RetroButton>
                <RetroButton onClick={handleUnstrUpload} disabled={uploading}>
                  {uploading ? "UPLOADING..." : "EXTRACT"}
                </RetroButton>
              </div>
            </div>
          </RetroCardContent>
        </RetroCard>
      )}

      {/* Processing state */}
      {extraction && extraction.status === "processing" && (
        <RetroCard>
          <RetroCardContent>
            <div className="flex items-center gap-3">
              <span className="text-xs tracking-wider animate-pulse" style={{ color: "var(--retro-amber)", fontFamily: "var(--font-display)" }}>
                EXTRACTING TEXT AND ENTITIES
              </span>
              <span className="blink-cursor text-sm" />
            </div>
          </RetroCardContent>
        </RetroCard>
      )}

      {/* Error */}
      {error && (
        <RetroCard>
          <RetroCardContent>
            <div className="flex items-start gap-3">
              <span className="text-xs font-bold shrink-0 px-2 py-0.5" style={{ backgroundColor: "var(--retro-terracotta)", color: "var(--retro-text)", borderRadius: "2px" }}>
                ERROR
              </span>
              <p className="text-xs" style={{ color: "var(--retro-text-dim)" }}>{error}</p>
            </div>
          </RetroCardContent>
        </RetroCard>
      )}

      {/* Confirm result */}
      {confirmResult && (
        <RetroCard accentTop>
          <RetroCardHeader>
            <GlowText as="h4" glow={false}>EXTRACTION CONFIRMED</GlowText>
          </RetroCardHeader>
          <RetroCardContent>
            <p className="text-sm" style={{ color: "var(--retro-sage)" }}>
              {confirmResult.records_created} health records created. View in ALL tab.
            </p>
          </RetroCardContent>
        </RetroCard>
      )}

      {/* Entity Review Panel */}
      {extraction && extraction.status === "awaiting_confirmation" && extraction.entities.length > 0 && !confirmResult && (
        <RetroCard accentTop>
          <RetroCardHeader>
            <div className="flex items-center justify-between">
              <GlowText as="h4" glow={false}>REVIEW EXTRACTED ENTITIES</GlowText>
              <span className="text-xs" style={{ color: "var(--retro-text-dim)" }}>
                {extraction.entities.length} entities found
              </span>
            </div>
          </RetroCardHeader>
          <RetroCardContent>
            <div className="space-y-4">
              {/* Patient selector */}
              <div>
                <label className="text-xs tracking-wider block mb-2" style={{ color: "var(--retro-text-dim)", fontFamily: "var(--font-display)" }}>
                  ASSIGN TO PATIENT
                </label>
                <select
                  value={selectedPatient}
                  onChange={(e) => setSelectedPatient(e.target.value)}
                  className="w-full px-3 py-2 text-sm border"
                  style={{
                    backgroundColor: "var(--retro-bg-deep)",
                    borderColor: "var(--retro-border)",
                    color: "var(--retro-text)",
                    fontFamily: "var(--font-mono)",
                    borderRadius: "2px",
                  }}
                >
                  {patients.map((p) => (
                    <option key={p.id} value={p.id}>{p.fhir_id || p.id.slice(0, 8)} ({p.gender || "unknown"})</option>
                  ))}
                </select>
              </div>

              {/* Entity table */}
              <div className="overflow-auto max-h-96">
                <RetroTable>
                  <RetroTableHeader>
                    <RetroTableRow>
                      <RetroTableHead className="w-10">{" "}</RetroTableHead>
                      <RetroTableHead>TYPE</RetroTableHead>
                      <RetroTableHead>TEXT</RetroTableHead>
                      <RetroTableHead>DETAILS</RetroTableHead>
                      <RetroTableHead className="w-16">CONF</RetroTableHead>
                    </RetroTableRow>
                  </RetroTableHeader>
                  <RetroTableBody>
                    {extraction.entities.map((entity, i) => (
                      <RetroTableRow key={i}>
                        <RetroTableCell>
                          <input
                            type="checkbox"
                            checked={selectedEntities.has(i)}
                            onChange={() => toggleEntity(i)}
                            className="accent-amber-500"
                          />
                        </RetroTableCell>
                        <RetroTableCell>
                          <span className="text-xs font-bold uppercase" style={{ color: ENTITY_COLORS[entity.entity_class] || "var(--retro-text-dim)" }}>
                            {entity.entity_class.replace("_", " ")}
                          </span>
                        </RetroTableCell>
                        <RetroTableCell>
                          <span className="text-xs" style={{ color: "var(--retro-text)" }}>{entity.text}</span>
                        </RetroTableCell>
                        <RetroTableCell>
                          <span className="text-xs" style={{ color: "var(--retro-text-muted)" }}>
                            {Object.entries(entity.attributes)
                              .filter(([k]) => k !== "medication_group")
                              .map(([k, v]) => `${k}: ${v}`)
                              .join(", ")
                              .slice(0, 60)}
                          </span>
                        </RetroTableCell>
                        <RetroTableCell>
                          <span className="text-xs" style={{ color: entity.confidence >= 0.8 ? "var(--retro-sage)" : "var(--retro-ochre)" }}>
                            {(entity.confidence * 100).toFixed(0)}%
                          </span>
                        </RetroTableCell>
                      </RetroTableRow>
                    ))}
                  </RetroTableBody>
                </RetroTable>
              </div>

              {/* Confirm button */}
              <div className="flex justify-end">
                <RetroButton onClick={handleConfirm} disabled={confirming || selectedEntities.size === 0}>
                  {confirming ? "SAVING..." : `CONFIRM & SAVE ${selectedEntities.size} ENTITIES`}
                </RetroButton>
              </div>
            </div>
          </RetroCardContent>
        </RetroCard>
      )}
    </div>
  );
}

/* ==========================================
   DEDUP TAB
   ========================================== */

function DedupTab() {
  const [candidates, setCandidates] = useState<DedupCandidate[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [scanResult, setScanResult] = useState<string | null>(null);
  const pageSize = 20;

  const fetchCandidates = (p = page) => {
    setLoading(true);
    api
      .get<{ items: DedupCandidate[]; total: number }>(`/dedup/candidates?page=${p}&limit=${pageSize}`)
      .then((data) => {
        setCandidates(data.items || []);
        setTotal(data.total || 0);
      })
      .catch(() => { setCandidates([]); setTotal(0); })
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchCandidates(page); }, [page]);

  const handleScan = async () => {
    setScanning(true);
    setError(null);
    setScanResult(null);
    try {
      const result = await api.post<{ candidates_found: number }>("/dedup/scan");
      setScanResult(`Scan complete. ${result.candidates_found} potential duplicates found.`);
      setPage(1);
      fetchCandidates(1);
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
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <RetroButton onClick={handleScan} disabled={scanning}>
          {scanning ? "SCANNING..." : "SCAN FOR DUPLICATES"}
        </RetroButton>
        {scanResult && (
          <span className="text-xs" style={{ color: "var(--retro-text-dim)" }}>
            {scanResult}
          </span>
        )}
      </div>

      {error && (
        <RetroCard>
          <RetroCardContent>
            <div className="flex items-start gap-3">
              <span
                className="text-xs font-bold shrink-0 px-2 py-0.5"
                style={{
                  backgroundColor: "var(--retro-terracotta)",
                  color: "var(--retro-text)",
                  borderRadius: "2px",
                }}
              >
                ERROR
              </span>
              <p className="text-xs" style={{ color: "var(--retro-text-dim)" }}>{error}</p>
            </div>
          </RetroCardContent>
        </RetroCard>
      )}

      {loading ? (
        <RetroLoadingState text="LOADING CANDIDATES" />
      ) : candidates.length === 0 && total === 0 ? (
        <div className="py-12 text-center">
          <p
            className="text-xs tracking-wider"
            style={{ color: "var(--retro-text-muted)" }}
          >
            NO DUPLICATE CANDIDATES FOUND
          </p>
          <p
            className="text-xs mt-1"
            style={{ color: "var(--retro-text-muted)" }}
          >
            Run the scanner to check for potential duplicates.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs" style={{ color: "var(--retro-text-dim)" }}>
              {total.toLocaleString()} PENDING CANDIDATES — SHOWING {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)}
            </span>
            <div className="flex gap-2">
              <RetroButton variant="ghost" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>PREV</RetroButton>
              <RetroButton variant="ghost" disabled={page * pageSize >= total} onClick={() => setPage(p => p + 1)}>NEXT</RetroButton>
            </div>
          </div>
          {candidates.map((candidate) => (
            <RetroCard key={candidate.id}>
              <RetroCardContent>
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span
                        className="text-sm font-medium"
                        style={{ color: "var(--retro-amber)" }}
                      >
                        {Math.round(candidate.similarity_score * 100)}% MATCH
                      </span>
                      <div className="flex gap-1">
                        {Object.entries(candidate.match_reasons)
                          .filter(([, matched]) => matched)
                          .map(([reason]) => (
                            <span
                              key={reason}
                              className="px-2 py-0.5 text-xs uppercase tracking-wider"
                              style={{
                                backgroundColor: "var(--retro-bg-surface)",
                                color: "var(--retro-text-dim)",
                                borderRadius: "2px",
                                border: "1px solid var(--retro-border)",
                              }}
                            >
                              {reason}
                            </span>
                          ))}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <RetroButton
                        onClick={() => handleMerge(candidate.id)}
                        disabled={actionLoading === candidate.id}
                      >
                        {actionLoading === candidate.id ? "..." : "MERGE"}
                      </RetroButton>
                      <RetroButton
                        variant="ghost"
                        onClick={() => handleDismiss(candidate.id)}
                        disabled={actionLoading === candidate.id}
                      >
                        DISMISS
                      </RetroButton>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {candidate.record_a && (
                      <DedupRecordCard label="RECORD A" record={candidate.record_a} />
                    )}
                    {candidate.record_b && (
                      <DedupRecordCard label="RECORD B" record={candidate.record_b} />
                    )}
                  </div>
                </div>
              </RetroCardContent>
            </RetroCard>
          ))}
        </div>
      )}
    </div>
  );
}

function DedupRecordCard({
  label,
  record,
}: {
  label: string;
  record: NonNullable<DedupCandidate["record_a"]>;
}) {
  return (
    <div
      className="border p-3 space-y-2"
      style={{
        backgroundColor: "var(--retro-bg-surface)",
        borderColor: "var(--retro-border)",
        borderRadius: "2px",
      }}
    >
      <div className="flex items-center gap-2">
        <span className="text-xs" style={{ color: "var(--retro-text-muted)" }}>
          {label}
        </span>
        <RetroBadge recordType={record.record_type} short />
      </div>
      <p className="text-sm" style={{ color: "var(--retro-text)" }}>
        {record.display_text}
      </p>
      <div className="flex items-center gap-3 text-xs" style={{ color: "var(--retro-text-muted)" }}>
        <span>{record.source_format}</span>
        <span>
          {record.effective_date
            ? new Date(record.effective_date).toLocaleDateString()
            : "--"}
        </span>
      </div>
    </div>
  );
}

/* ==========================================
   SYSTEM TAB
   ========================================== */

function SystemTab() {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const { clearTokens } = useAuthStore();

  useEffect(() => {
    Promise.all([
      api.get<UserResponse>("/auth/me").catch(() => null),
      api.get<DashboardOverview>("/dashboard/overview").catch(() => null),
    ])
      .then(([userData, overviewData]) => {
        setUser(userData);
        setOverview(overviewData);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <RetroLoadingState text="LOADING SYSTEM INFO" />;

  const dateRange =
    overview?.date_range_start && overview?.date_range_end
      ? `${new Date(overview.date_range_start).toLocaleDateString()} – ${new Date(overview.date_range_end).toLocaleDateString()}`
      : "N/A";

  return (
    <div className="space-y-4">
      {/* Account Info */}
      <RetroCard accentTop>
        <RetroCardHeader>
          <GlowText as="h4" glow={false}>ACCOUNT INFORMATION</GlowText>
        </RetroCardHeader>
        <RetroCardContent>
          {user ? (
            <div className="space-y-2">
              <SysRow label="EMAIL" value={user.email} />
              <SysRow label="DISPLAY NAME" value={user.display_name || "Not set"} />
              <SysRow
                label="STATUS"
                value={user.is_active ? "ACTIVE" : "INACTIVE"}
                valueColor={user.is_active ? "var(--retro-sage)" : "var(--retro-terracotta)"}
              />
              <SysRow label="USER ID" value={user.id} mono />
            </div>
          ) : (
            <p className="text-xs" style={{ color: "var(--retro-text-muted)" }}>
              Unable to load account information.
            </p>
          )}
        </RetroCardContent>
      </RetroCard>

      {/* Data Stats */}
      <RetroCard>
        <RetroCardHeader>
          <GlowText as="h4" glow={false}>DATA STATISTICS</GlowText>
        </RetroCardHeader>
        <RetroCardContent>
          {overview ? (
            <div className="space-y-2">
              <SysRow label="TOTAL RECORDS" value={String(overview.total_records)} />
              <SysRow label="TOTAL PATIENTS" value={String(overview.total_patients)} />
              <SysRow label="TOTAL UPLOADS" value={String(overview.total_uploads)} />
              <SysRow label="DATE RANGE" value={dateRange} />
            </div>
          ) : (
            <p className="text-xs" style={{ color: "var(--retro-text-muted)" }}>
              No data available.
            </p>
          )}
        </RetroCardContent>
      </RetroCard>

      {/* Sign Out */}
      <RetroButton
        variant="destructive"
        onClick={() => {
          clearTokens();
          window.location.href = "/login";
        }}
      >
        SIGN OUT
      </RetroButton>

      {/* Privacy Notice */}
      <RetroCard>
        <RetroCardContent>
          <div className="flex items-start gap-3">
            <span
              className="text-xs font-bold shrink-0 px-2 py-0.5"
              style={{
                backgroundColor: "var(--retro-sienna)",
                color: "var(--retro-text)",
                borderRadius: "2px",
              }}
            >
              NOTICE
            </span>
            <p
              className="text-xs leading-relaxed"
              style={{ color: "var(--retro-text-dim)" }}
            >
              All health data is stored locally and encrypted at rest. No data is
              transmitted to external services. AI summary prompts are constructed
              locally with de-identified data and are never sent automatically.
            </p>
          </div>
        </RetroCardContent>
      </RetroCard>
    </div>
  );
}

function SysRow({
  label,
  value,
  mono,
  valueColor,
}: {
  label: string;
  value: string;
  mono?: boolean;
  valueColor?: string;
}) {
  return (
    <div
      className="flex items-baseline justify-between py-1.5 border-b"
      style={{ borderColor: "var(--retro-border)" }}
    >
      <span
        className="text-xs uppercase tracking-wider"
        style={{ color: "var(--retro-text-muted)" }}
      >
        {label}
      </span>
      <span
        className={`text-xs ${mono ? "font-mono" : "font-medium"}`}
        style={{ color: valueColor || "var(--retro-text)" }}
      >
        {value}
      </span>
    </div>
  );
}
