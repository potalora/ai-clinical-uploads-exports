"use client";

import { useCallback, useEffect, useState } from "react";
import { useDropzone } from "react-dropzone";
import { FolderUp, FileText, FileArchive, ChevronDown, ChevronUp } from "lucide-react";
import { useDirectoryUpload } from "@/hooks/useDirectoryUpload";
import { getFilesFromDrop } from "@/lib/getFilesFromDrop";
import { api } from "@/lib/api";
import type {
  UploadResponse,
  UnstructuredUploadResponse,
  ExtractionResult,
  ExtractedEntity,
  PatientInfo,
  TriggerExtractionResponse,
} from "@/types/api";
import { GlowText } from "@/components/retro/GlowText";
import { RetroCard, RetroCardHeader, RetroCardContent } from "@/components/retro/RetroCard";
import { RetroButton } from "@/components/retro/RetroButton";
import { RetroLoadingState } from "@/components/retro/RetroLoadingState";
import {
  RetroTable,
  RetroTableHeader,
  RetroTableHead,
  RetroTableBody,
  RetroTableRow,
  RetroTableCell,
} from "@/components/retro/RetroTable";

/* ==========================================
   FILE CLASSIFICATION HELPERS
   ========================================== */

const STRUCTURED_EXTENSIONS = new Set([".json", ".zip", ".tsv"]);
const UNSTRUCTURED_EXTENSIONS = new Set([".pdf", ".rtf", ".tif", ".tiff"]);

function getExtension(filename: string): string {
  const dot = filename.lastIndexOf(".");
  return dot >= 0 ? filename.slice(dot).toLowerCase() : "";
}

function isStructured(file: File): boolean {
  return STRUCTURED_EXTENSIONS.has(getExtension(file.name));
}

function isUnstructured(file: File): boolean {
  return UNSTRUCTURED_EXTENSIONS.has(getExtension(file.name));
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/* ==========================================
   UPLOAD HISTORY TYPES
   ========================================== */

interface UploadHistoryItem {
  id: string;
  original_filename: string;
  ingestion_status: string;
  records_inserted?: number;
  created_at: string;
  file_category?: string;
}

/* ==========================================
   UPLOAD RESULT TRACKING
   ========================================== */

interface UploadResult {
  type: "structured" | "unstructured";
  filename: string;
  response?: UploadResponse | UnstructuredUploadResponse;
  error?: string;
}

/* ==========================================
   ENTITY COLORS
   ========================================== */

const ENTITY_COLORS: Record<string, string> = {
  medication: "var(--theme-amber)",
  condition: "var(--theme-ochre)",
  lab_result: "var(--theme-sage)",
  vital: "var(--theme-sage)",
  procedure: "var(--record-procedure-text)",
  allergy: "var(--theme-terracotta)",
  provider: "var(--theme-text-dim)",
};

/* ==========================================
   MAIN UPLOAD PAGE
   ========================================== */

export default function UploadPage() {
  // --- File selection state ---
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);

  // --- Upload state ---
  const [uploading, setUploading] = useState(false);
  const [uploadResults, setUploadResults] = useState<UploadResult[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // --- Extraction tracking (for unstructured uploads) ---
  const [activeExtractions, setActiveExtractions] = useState<
    Array<{ uploadId: string; filename: string; extraction: ExtractionResult | null }>
  >([]);
  const [selectedEntities, setSelectedEntities] = useState<Record<string, Set<number>>>({});

  // --- Patient selection for entity confirmation ---
  const [patients, setPatients] = useState<PatientInfo[]>([]);
  const [selectedPatient, setSelectedPatient] = useState("");
  const [confirming, setConfirming] = useState<string | null>(null);
  const [confirmResults, setConfirmResults] = useState<Record<string, number>>({});

  // --- Upload history ---
  const [historyOpen, setHistoryOpen] = useState(false);
  const [history, setHistory] = useState<UploadHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);

  // --- Extraction trigger state (for unstructured files from ZIP uploads) ---
  const [pendingExtractions, setPendingExtractions] = useState<
    { upload_id: string; filename: string; status: string }[]
  >([]);
  const [selectedForExtraction, setSelectedForExtraction] = useState<Set<string>>(
    new Set()
  );
  const [extractionTriggered, setExtractionTriggered] = useState(false);
  const [extractionStatuses, setExtractionStatuses] = useState<
    Record<string, string>
  >({});

  // --- Directory upload (client-side zipping) ---
  const {
    folderInputRef,
    isZipping,
    zipProgress,
    folderInfo,
    selectFolder,
    handleFolderSelect,
    createZipFromFiles,
    clearFolderInfo,
  } = useDirectoryUpload({
    onZipReady: (file) => {
      setSelectedFiles((prev) => [...prev, file]);
      setUploadResults([]);
      setUploadError(null);
    },
    onError: (message) => setUploadError(message),
  });

  // --- Load patients for entity confirmation ---
  useEffect(() => {
    (async () => {
      try {
        const data = await api.get<{ items: PatientInfo[] }>("/dashboard/patients");
        setPatients(data.items);
        if (data.items.length > 0) setSelectedPatient(data.items[0].id);
      } catch {
        /* ignore */
      }
    })();
  }, []);

  // --- Load history when section is opened ---
  useEffect(() => {
    if (!historyOpen || historyLoaded) return;
    setHistoryLoading(true);
    api
      .get<{ items: UploadHistoryItem[]; total: number }>("/upload/history")
      .then((data) => {
        setHistory(data.items || []);
        setHistoryLoaded(true);
      })
      .catch(() => setHistory([]))
      .finally(() => setHistoryLoading(false));
  }, [historyOpen, historyLoaded]);

  // --- Poll for extraction results ---
  useEffect(() => {
    const pending = activeExtractions.filter(
      (e) => e.extraction === null || e.extraction.status === "processing"
    );
    if (pending.length === 0) return;

    const interval = setInterval(async () => {
      for (const entry of pending) {
        try {
          const data = await api.get<ExtractionResult>(
            `/upload/${entry.uploadId}/extraction`
          );
          setActiveExtractions((prev) =>
            prev.map((e) =>
              e.uploadId === entry.uploadId ? { ...e, extraction: data } : e
            )
          );
          if (
            data.status === "awaiting_confirmation" ||
            data.status === "completed" ||
            data.status === "failed"
          ) {
            if (data.entities.length > 0) {
              setSelectedEntities((prev) => ({
                ...prev,
                [entry.uploadId]: new Set(data.entities.map((_, i) => i)),
              }));
            }
          }
        } catch {
          /* continue polling */
        }
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [activeExtractions]);

  // --- Drop handler ---
  const onDrop = useCallback((acceptedFiles: File[]) => {
    if (acceptedFiles.length > 0) {
      setSelectedFiles((prev) => [...prev, ...acceptedFiles]);
      setUploadResults([]);
      setUploadError(null);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/json": [".json"],
      "application/zip": [".zip"],
      "application/x-zip-compressed": [".zip"],
      "text/tab-separated-values": [".tsv"],
      "application/pdf": [".pdf"],
      "application/rtf": [".rtf"],
      "text/rtf": [".rtf"],
      "image/tiff": [".tif", ".tiff"],
    },
    multiple: true,
  });

  // --- Clear all selected files ---
  const clearFiles = useCallback(() => {
    setSelectedFiles([]);
    setUploadResults([]);
    setUploadError(null);
    clearFolderInfo();
  }, [clearFolderInfo]);

  // --- Upload all files ---
  const handleUploadAll = useCallback(async () => {
    if (selectedFiles.length === 0) return;
    setUploading(true);
    setUploadError(null);
    setUploadResults([]);
    setActiveExtractions([]);
    setConfirmResults({});

    const results: UploadResult[] = [];

    // Separate structured vs unstructured
    const structured = selectedFiles.filter(isStructured);
    const unstructured = selectedFiles.filter(isUnstructured);

    // Upload structured files one at a time
    for (const file of structured) {
      try {
        const formData = new FormData();
        formData.append("file", file);
        const resp = await api.postForm<UploadResponse>("/upload", formData);
        results.push({ type: "structured", filename: file.name, response: resp });
        if (resp.unstructured_uploads && resp.unstructured_uploads.length > 0) {
          setPendingExtractions((prev) => [...prev, ...resp.unstructured_uploads!]);
        }
      } catch (err) {
        results.push({
          type: "structured",
          filename: file.name,
          error: err instanceof Error ? err.message : "Upload failed",
        });
      }
    }

    // Upload unstructured files
    if (unstructured.length === 1) {
      // Single unstructured file
      const file = unstructured[0];
      try {
        const formData = new FormData();
        formData.append("file", file);
        const resp = await api.postForm<UnstructuredUploadResponse>(
          "/upload/unstructured",
          formData
        );
        results.push({ type: "unstructured", filename: file.name, response: resp });
        setActiveExtractions((prev) => [
          ...prev,
          { uploadId: resp.upload_id, filename: file.name, extraction: null },
        ]);
      } catch (err) {
        results.push({
          type: "unstructured",
          filename: file.name,
          error: err instanceof Error ? err.message : "Upload failed",
        });
      }
    } else if (unstructured.length > 1) {
      // Batch unstructured
      try {
        const formData = new FormData();
        for (const file of unstructured) {
          formData.append("files", file);
        }
        const resp = await api.postForm<{
          uploads: UnstructuredUploadResponse[];
        }>("/upload/unstructured-batch", formData);
        for (let i = 0; i < resp.uploads.length; i++) {
          const upload = resp.uploads[i];
          const filename = unstructured[i]?.name || `file-${i}`;
          results.push({ type: "unstructured", filename, response: upload });
          setActiveExtractions((prev) => [
            ...prev,
            { uploadId: upload.upload_id, filename, extraction: null },
          ]);
        }
      } catch (err) {
        for (const file of unstructured) {
          results.push({
            type: "unstructured",
            filename: file.name,
            error: err instanceof Error ? err.message : "Batch upload failed",
          });
        }
      }
    }

    setUploadResults(results);
    setSelectedFiles([]);
    setUploading(false);
    // Refresh history on next open
    setHistoryLoaded(false);
  }, [selectedFiles]);

  // --- Extraction trigger handlers ---
  const handleTriggerExtraction = useCallback(async () => {
    if (selectedForExtraction.size === 0) return;
    setExtractionTriggered(true);

    const ids = Array.from(selectedForExtraction);

    try {
      const resp = await api.post<TriggerExtractionResponse>(
        "/upload/trigger-extraction",
        { upload_ids: ids }
      );

      const statuses: Record<string, string> = {};
      for (const r of resp.results) {
        statuses[r.upload_id] = r.status;
      }
      setExtractionStatuses(statuses);

      // Start polling for each triggered file
      const processingIds = resp.results
        .filter((r) => r.status === "processing")
        .map((r) => r.upload_id);

      for (const uploadId of processingIds) {
        pollExtractionStatus(uploadId);
      }
    } catch {
      setExtractionTriggered(false);
    }
  }, [selectedForExtraction]);

  const pollExtractionStatus = useCallback(
    (uploadId: string) => {
      const interval = setInterval(async () => {
        try {
          const status = await api.get<{ ingestion_status: string }>(
            `/upload/${uploadId}/status`
          );
          setExtractionStatuses((prev) => ({
            ...prev,
            [uploadId]: status.ingestion_status,
          }));
          if (
            status.ingestion_status === "awaiting_confirmation" ||
            status.ingestion_status === "failed" ||
            status.ingestion_status === "completed"
          ) {
            clearInterval(interval);
            if (status.ingestion_status === "awaiting_confirmation") {
              const pending = pendingExtractions.find(
                (p) => p.upload_id === uploadId
              );
              setActiveExtractions((prev) => [
                ...prev,
                {
                  uploadId,
                  filename: pending?.filename || uploadId,
                  extraction: null,
                },
              ]);
            }
          }
        } catch {
          clearInterval(interval);
        }
      }, 2000);
    },
    [pendingExtractions]
  );

  const handleDismissExtractionPanel = useCallback(() => {
    setPendingExtractions([]);
    setSelectedForExtraction(new Set());
    setExtractionTriggered(false);
    setExtractionStatuses({});
  }, []);

  const toggleExtractionSelection = useCallback((uploadId: string) => {
    setSelectedForExtraction((prev) => {
      const next = new Set(prev);
      if (next.has(uploadId)) next.delete(uploadId);
      else next.add(uploadId);
      return next;
    });
  }, []);

  const toggleSelectAllExtraction = useCallback(() => {
    if (selectedForExtraction.size === pendingExtractions.length) {
      setSelectedForExtraction(new Set());
    } else {
      setSelectedForExtraction(
        new Set(pendingExtractions.map((p) => p.upload_id))
      );
    }
  }, [pendingExtractions, selectedForExtraction]);

  // --- Entity toggle ---
  const toggleEntity = useCallback((uploadId: string, index: number) => {
    setSelectedEntities((prev) => {
      const current = new Set(prev[uploadId] || []);
      if (current.has(index)) current.delete(index);
      else current.add(index);
      return { ...prev, [uploadId]: current };
    });
  }, []);

  // --- Confirm entities ---
  const handleConfirm = useCallback(
    async (uploadId: string, entities: ExtractedEntity[]) => {
      if (!selectedPatient) return;
      setConfirming(uploadId);

      try {
        const selected = selectedEntities[uploadId] || new Set();
        const confirmed = entities
          .filter((_, i) => selected.has(i))
          .map((e) => ({
            entity_class: e.entity_class,
            text: e.text,
            attributes: e.attributes,
            start_pos: e.start_pos,
            end_pos: e.end_pos,
            confidence: e.confidence,
          }));

        const resp = await api.post<{ records_created: number }>(
          `/upload/${uploadId}/confirm-extraction`,
          { confirmed_entities: confirmed, patient_id: selectedPatient }
        );
        setConfirmResults((prev) => ({
          ...prev,
          [uploadId]: resp.records_created,
        }));
      } catch (err) {
        setUploadError(
          err instanceof Error ? err.message : "Confirmation failed"
        );
      } finally {
        setConfirming(null);
      }
    },
    [selectedPatient, selectedEntities]
  );

  // --- Directory drop handler (intercepts before react-dropzone) ---
  const handleDropCapture = useCallback(
    async (e: React.DragEvent<HTMLDivElement>) => {
      if (!e.dataTransfer) return;
      const result = await getFilesFromDrop(e.dataTransfer);
      if (result) {
        // Directory was dropped — prevent react-dropzone from processing
        e.stopPropagation();
        e.preventDefault();
        createZipFromFiles(result.files, result.folderName);
      }
      // If result is null, individual files were dropped — let react-dropzone handle it
    },
    [createZipFromFiles]
  );

  // --- Derived counts ---
  const structuredCount = selectedFiles.filter(isStructured).length;
  const unstructuredCount = selectedFiles.filter(isUnstructured).length;

  // --- Render ---
  return (
    <div className="space-y-6 retro-stagger">
      <GlowText as="h1">Upload</GlowText>

      {/* ==========================================
          HERO DROPZONE
          ========================================== */}
      <RetroCard accentTop>
        <RetroCardContent>
          <div
            {...getRootProps()}
            onDropCapture={handleDropCapture}
            className="border-2 border-dashed transition-all duration-200 cursor-pointer"
            style={{
              borderColor: isDragActive
                ? "var(--theme-amber)"
                : "var(--theme-border)",
              backgroundColor: isDragActive
                ? "var(--theme-bg-card-hover)"
                : "transparent",
              borderRadius: "6px",
              minHeight: "200px",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              padding: "2rem",
            }}
          >
            <input {...getInputProps()} />
            <FolderUp
              size={48}
              style={{ color: "var(--theme-text-muted)", marginBottom: "1rem" }}
            />
            <p
              style={{
                color: "var(--theme-text)",
                fontFamily: "var(--font-body)",
                fontWeight: 600,
                fontSize: "1rem",
                marginBottom: "0.25rem",
              }}
            >
              Drop files or folders
            </p>
            <p
              style={{
                color: "var(--theme-text-dim)",
                fontFamily: "var(--font-body)",
                fontSize: "0.8rem",
              }}
            >
              JSON, ZIP, PDF, RTF, TIFF, or Epic export directories
            </p>
          </div>

          {/* Buttons below dropzone */}
          <div
            style={{
              display: "flex",
              gap: "0.75rem",
              justifyContent: "center",
              marginTop: "1rem",
            }}
          >
            <RetroButton
              variant="ghost"
              onClick={(e) => {
                e.stopPropagation();
                // Trigger the dropzone file picker
                const input = document.querySelector(
                  'input[type="file"]:not([webkitdirectory])'
                ) as HTMLInputElement | null;
                input?.click();
              }}
            >
              <FileText size={14} style={{ marginRight: "0.5rem" }} />
              Select Files
            </RetroButton>
            <RetroButton
              onClick={(e) => {
                e.stopPropagation();
                selectFolder();
              }}
              disabled={isZipping}
            >
              <FileArchive size={14} style={{ marginRight: "0.5rem" }} />
              Select Folder
            </RetroButton>
            {/* Hidden folder input */}
            <input
              ref={folderInputRef}
              type="file"
              webkitdirectory=""
              directory=""
              multiple
              onChange={handleFolderSelect}
              style={{ display: "none" }}
            />
          </div>
        </RetroCardContent>
      </RetroCard>

      {/* ==========================================
          ZIPPING PROGRESS
          ========================================== */}
      {isZipping && folderInfo && (
        <RetroCard>
          <RetroCardContent>
            <span
              className="animate-pulse"
              style={{
                fontFamily: "VT323, monospace",
                fontSize: "1.1rem",
                color: "var(--theme-amber)",
                display: "block",
                marginBottom: "0.5rem",
              }}
            >
              Preparing upload...
            </span>
            <p
              style={{
                fontSize: "0.8rem",
                color: "var(--theme-text-dim)",
                fontFamily: "var(--font-body)",
                marginBottom: "0.75rem",
              }}
            >
              {folderInfo.name} &mdash; {folderInfo.fileCount.toLocaleString()} files ({formatFileSize(folderInfo.totalSize)})
            </p>
            <div
              style={{
                height: "6px",
                backgroundColor: "var(--theme-bg-deep)",
                borderRadius: "3px",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  height: "100%",
                  width: `${zipProgress}%`,
                  backgroundColor: "var(--theme-amber)",
                  borderRadius: "3px",
                  transition: "width 0.2s ease",
                }}
              />
            </div>
            <span
              style={{
                fontFamily: "VT323, monospace",
                fontSize: "0.95rem",
                color: "var(--theme-amber)",
                display: "block",
                textAlign: "right",
                marginTop: "0.25rem",
              }}
            >
              {zipProgress.toFixed(0)}%
            </span>
          </RetroCardContent>
        </RetroCard>
      )}

      {/* ==========================================
          SELECTED FILES DISPLAY
          ========================================== */}
      {selectedFiles.length > 0 && (
        <RetroCard>
          <RetroCardContent>
            {/* Status bar */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: "1rem",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                <span
                  style={{
                    fontFamily: "VT323, monospace",
                    fontSize: "1.1rem",
                    color: "var(--theme-amber)",
                  }}
                >
                  {selectedFiles.length} file{selectedFiles.length !== 1 ? "s" : ""}{" "}
                  selected
                </span>

                {structuredCount > 0 && (
                  <span
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.25rem",
                      padding: "0.15rem 0.5rem",
                      borderRadius: "4px",
                      fontSize: "0.7rem",
                      fontFamily: "var(--font-body)",
                      fontWeight: 600,
                      backgroundColor: "var(--theme-sage)",
                      color: "var(--theme-bg-deep)",
                    }}
                  >
                    {structuredCount} structured &rarr; Import
                  </span>
                )}

                {unstructuredCount > 0 && (
                  <span
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.25rem",
                      padding: "0.15rem 0.5rem",
                      borderRadius: "4px",
                      fontSize: "0.7rem",
                      fontFamily: "var(--font-body)",
                      fontWeight: 600,
                      backgroundColor: "var(--theme-amber)",
                      color: "var(--theme-bg-deep)",
                    }}
                  >
                    {unstructuredCount} document{unstructuredCount !== 1 ? "s" : ""}{" "}
                    &rarr; AI extraction
                  </span>
                )}
              </div>

              <RetroButton variant="ghost" onClick={clearFiles}>
                Clear
              </RetroButton>
            </div>

            {/* File list */}
            <div
              style={{
                maxHeight: "180px",
                overflowY: "auto",
                borderRadius: "4px",
                backgroundColor: "var(--theme-bg-deep)",
                padding: "0.5rem",
              }}
            >
              {selectedFiles.map((file, i) => (
                <div
                  key={`${file.name}-${i}`}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "0.35rem 0.5rem",
                    borderBottom:
                      i < selectedFiles.length - 1
                        ? "1px solid var(--theme-border)"
                        : "none",
                  }}
                >
                  <span
                    style={{
                      fontFamily: "VT323, monospace",
                      fontSize: "0.95rem",
                      color: "var(--theme-text)",
                    }}
                  >
                    {file.name}
                  </span>
                  <span
                    style={{
                      fontFamily: "VT323, monospace",
                      fontSize: "0.85rem",
                      color: "var(--theme-text-muted)",
                    }}
                  >
                    {formatFileSize(file.size)}
                  </span>
                </div>
              ))}
            </div>

            {/* Upload All button */}
            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "1rem" }}>
              <RetroButton onClick={handleUploadAll} disabled={uploading}>
                {uploading ? "Uploading..." : "Upload All"}
              </RetroButton>
            </div>
          </RetroCardContent>
        </RetroCard>
      )}

      {/* ==========================================
          UPLOAD PROGRESS / RESULTS
          ========================================== */}
      {uploading && (
        <RetroCard>
          <RetroCardContent>
            <span
              className="animate-pulse"
              style={{
                fontFamily: "VT323, monospace",
                fontSize: "1.1rem",
                color: "var(--theme-amber)",
              }}
            >
              Uploading files...
            </span>
          </RetroCardContent>
        </RetroCard>
      )}

      {uploadError && (
        <RetroCard>
          <RetroCardContent>
            <div style={{ display: "flex", alignItems: "flex-start", gap: "0.75rem" }}>
              <span
                style={{
                  fontSize: "0.7rem",
                  fontWeight: 700,
                  padding: "0.15rem 0.5rem",
                  borderRadius: "4px",
                  backgroundColor: "var(--theme-terracotta)",
                  color: "var(--theme-text)",
                  flexShrink: 0,
                  fontFamily: "var(--font-body)",
                }}
              >
                ERROR
              </span>
              <p
                style={{
                  fontSize: "0.8rem",
                  color: "var(--theme-text-dim)",
                  fontFamily: "var(--font-body)",
                }}
              >
                {uploadError}
              </p>
            </div>
          </RetroCardContent>
        </RetroCard>
      )}

      {uploadResults.length > 0 && !uploading && (
        <RetroCard accentTop>
          <RetroCardHeader>
            <GlowText as="h4" glow={false}>
              Upload complete
            </GlowText>
          </RetroCardHeader>
          <RetroCardContent>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {uploadResults.map((result, i) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "0.5rem 0",
                    borderBottom:
                      i < uploadResults.length - 1
                        ? "1px solid var(--theme-border)"
                        : "none",
                  }}
                >
                  <span
                    style={{
                      fontFamily: "VT323, monospace",
                      fontSize: "0.95rem",
                      color: "var(--theme-text)",
                    }}
                  >
                    {result.filename}
                  </span>
                  {result.error ? (
                    <span
                      style={{
                        fontSize: "0.7rem",
                        fontWeight: 600,
                        color: "var(--theme-terracotta)",
                        fontFamily: "var(--font-body)",
                      }}
                    >
                      {result.error}
                    </span>
                  ) : result.type === "structured" &&
                    result.response &&
                    "records_inserted" in result.response ? (
                    <span
                      style={{
                        fontSize: "0.7rem",
                        fontWeight: 600,
                        color: "var(--theme-sage)",
                        fontFamily: "var(--font-body)",
                      }}
                    >
                      {(result.response as UploadResponse).records_inserted} records
                      inserted
                    </span>
                  ) : (
                    <span
                      style={{
                        fontSize: "0.7rem",
                        fontWeight: 600,
                        color: "var(--theme-amber)",
                        fontFamily: "var(--font-body)",
                      }}
                    >
                      Extracting...
                    </span>
                  )}
                </div>
              ))}

              {/* Show structured upload errors if any */}
              {uploadResults
                .filter(
                  (r) =>
                    r.type === "structured" &&
                    r.response &&
                    "errors" in r.response &&
                    Array.isArray((r.response as UploadResponse).errors) &&
                    (r.response as UploadResponse).errors.length > 0
                )
                .map((r, i) => (
                  <div key={`errs-${i}`} style={{ marginTop: "0.5rem" }}>
                    <p
                      style={{
                        fontSize: "0.75rem",
                        fontWeight: 600,
                        color: "var(--theme-terracotta)",
                        fontFamily: "var(--font-body)",
                        marginBottom: "0.25rem",
                      }}
                    >
                      Errors in {r.filename}
                    </p>
                    <div
                      style={{
                        maxHeight: "120px",
                        overflowY: "auto",
                        display: "flex",
                        flexDirection: "column",
                        gap: "0.25rem",
                      }}
                    >
                      {(r.response as UploadResponse).errors.map((err, j) => (
                        <p
                          key={j}
                          style={{
                            fontFamily: "VT323, monospace",
                            fontSize: "0.85rem",
                            padding: "0.35rem 0.5rem",
                            backgroundColor: "var(--theme-bg-deep)",
                            color: "var(--theme-text-dim)",
                            borderRadius: "4px",
                          }}
                        >
                          {typeof err === "string" ? err : JSON.stringify(err)}
                        </p>
                      ))}
                    </div>
                  </div>
                ))}
            </div>
          </RetroCardContent>
        </RetroCard>
      )}

      {/* ==========================================
          ENTITY REVIEW PANELS (for each unstructured extraction)
          ========================================== */}
      {activeExtractions.map((entry) => {
        const ext = entry.extraction;

        // Still processing
        if (!ext || ext.status === "processing") {
          return (
            <RetroCard key={entry.uploadId}>
              <RetroCardContent>
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                  <span
                    className="animate-pulse"
                    style={{
                      fontFamily: "VT323, monospace",
                      fontSize: "1rem",
                      color: "var(--theme-amber)",
                    }}
                  >
                    Extracting entities from {entry.filename}...
                  </span>
                </div>
              </RetroCardContent>
            </RetroCard>
          );
        }

        // Confirmed
        if (confirmResults[entry.uploadId] !== undefined) {
          return (
            <RetroCard key={entry.uploadId} accentTop>
              <RetroCardHeader>
                <GlowText as="h4" glow={false}>
                  Extraction confirmed &mdash; {entry.filename}
                </GlowText>
              </RetroCardHeader>
              <RetroCardContent>
                <p
                  style={{
                    fontSize: "0.85rem",
                    color: "var(--theme-sage)",
                    fontFamily: "var(--font-body)",
                  }}
                >
                  {confirmResults[entry.uploadId]} health records created.
                </p>
              </RetroCardContent>
            </RetroCard>
          );
        }

        // Failed
        if (ext.status === "failed" || ext.error) {
          return (
            <RetroCard key={entry.uploadId}>
              <RetroCardContent>
                <div style={{ display: "flex", alignItems: "flex-start", gap: "0.75rem" }}>
                  <span
                    style={{
                      fontSize: "0.7rem",
                      fontWeight: 700,
                      padding: "0.15rem 0.5rem",
                      borderRadius: "4px",
                      backgroundColor: "var(--theme-terracotta)",
                      color: "var(--theme-text)",
                      flexShrink: 0,
                      fontFamily: "var(--font-body)",
                    }}
                  >
                    ERROR
                  </span>
                  <p
                    style={{
                      fontSize: "0.8rem",
                      color: "var(--theme-text-dim)",
                      fontFamily: "var(--font-body)",
                    }}
                  >
                    {ext.error || "Extraction failed"} ({entry.filename})
                  </p>
                </div>
              </RetroCardContent>
            </RetroCard>
          );
        }

        // Awaiting confirmation with entities
        if (
          ext.status === "awaiting_confirmation" &&
          ext.entities.length > 0
        ) {
          const entitiesSelected = selectedEntities[entry.uploadId] || new Set();
          return (
            <RetroCard key={entry.uploadId} accentTop>
              <RetroCardHeader>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                  }}
                >
                  <GlowText as="h4" glow={false}>
                    Review &mdash; {entry.filename}
                  </GlowText>
                  <span
                    style={{
                      fontSize: "0.75rem",
                      color: "var(--theme-text-dim)",
                      fontFamily: "var(--font-body)",
                    }}
                  >
                    {ext.entities.length} entities found
                  </span>
                </div>
              </RetroCardHeader>
              <RetroCardContent>
                <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                  {/* Extracted text preview */}
                  {ext.extracted_text_preview && (
                    <div
                      style={{
                        padding: "0.75rem",
                        backgroundColor: "var(--theme-bg-deep)",
                        borderRadius: "4px",
                        maxHeight: "100px",
                        overflowY: "auto",
                      }}
                    >
                      <p
                        style={{
                          fontFamily: "VT323, monospace",
                          fontSize: "0.85rem",
                          color: "var(--theme-text-dim)",
                          whiteSpace: "pre-wrap",
                        }}
                      >
                        {ext.extracted_text_preview}
                      </p>
                    </div>
                  )}

                  {/* Patient selector */}
                  <div>
                    <label
                      style={{
                        display: "block",
                        fontSize: "0.75rem",
                        fontWeight: 600,
                        marginBottom: "0.35rem",
                        color: "var(--theme-text-dim)",
                        fontFamily: "var(--font-body)",
                      }}
                    >
                      Assign to patient
                    </label>
                    <select
                      value={selectedPatient}
                      onChange={(e) => setSelectedPatient(e.target.value)}
                      style={{
                        width: "100%",
                        padding: "0.4rem 0.75rem",
                        fontSize: "0.8rem",
                        border: "1px solid var(--theme-border)",
                        backgroundColor: "var(--theme-bg-deep)",
                        color: "var(--theme-text)",
                        fontFamily: "VT323, monospace",
                        borderRadius: "4px",
                      }}
                    >
                      {patients.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.fhir_id || p.id.slice(0, 8)} ({p.gender || "unknown"})
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Entity table */}
                  <div style={{ overflowX: "auto", maxHeight: "320px", overflowY: "auto" }}>
                    <RetroTable>
                      <RetroTableHeader>
                        <RetroTableHead className="w-10"> </RetroTableHead>
                        <RetroTableHead>Type</RetroTableHead>
                        <RetroTableHead>Text</RetroTableHead>
                        <RetroTableHead>Details</RetroTableHead>
                        <RetroTableHead className="w-16">Conf</RetroTableHead>
                      </RetroTableHeader>
                      <RetroTableBody>
                        {ext.entities.map((entity, i) => (
                          <RetroTableRow key={i}>
                            <RetroTableCell>
                              <input
                                type="checkbox"
                                checked={entitiesSelected.has(i)}
                                onChange={() => toggleEntity(entry.uploadId, i)}
                                className="accent-amber-500"
                              />
                            </RetroTableCell>
                            <RetroTableCell>
                              <span
                                style={{
                                  fontSize: "0.7rem",
                                  fontWeight: 600,
                                  color:
                                    ENTITY_COLORS[entity.entity_class] ||
                                    "var(--theme-text-dim)",
                                  fontFamily: "var(--font-body)",
                                }}
                              >
                                {entity.entity_class.replace("_", " ")}
                              </span>
                            </RetroTableCell>
                            <RetroTableCell>
                              <span
                                style={{
                                  fontSize: "0.75rem",
                                  color: "var(--theme-text)",
                                  fontFamily: "var(--font-body)",
                                }}
                              >
                                {entity.text}
                              </span>
                            </RetroTableCell>
                            <RetroTableCell>
                              <span
                                style={{
                                  fontSize: "0.7rem",
                                  color: "var(--theme-text-muted)",
                                  fontFamily: "var(--font-body)",
                                }}
                              >
                                {Object.entries(entity.attributes)
                                  .filter(([k]) => k !== "medication_group")
                                  .map(([k, v]) => `${k}: ${v}`)
                                  .join(", ")
                                  .slice(0, 60)}
                              </span>
                            </RetroTableCell>
                            <RetroTableCell>
                              <span
                                style={{
                                  fontSize: "0.7rem",
                                  fontFamily: "VT323, monospace",
                                  color:
                                    entity.confidence >= 0.8
                                      ? "var(--theme-sage)"
                                      : "var(--theme-ochre)",
                                }}
                              >
                                {(entity.confidence * 100).toFixed(0)}%
                              </span>
                            </RetroTableCell>
                          </RetroTableRow>
                        ))}
                      </RetroTableBody>
                    </RetroTable>
                  </div>

                  {/* Confirm button */}
                  <div style={{ display: "flex", justifyContent: "flex-end" }}>
                    <RetroButton
                      onClick={() => handleConfirm(entry.uploadId, ext.entities)}
                      disabled={
                        confirming === entry.uploadId || entitiesSelected.size === 0
                      }
                    >
                      {confirming === entry.uploadId
                        ? "Saving..."
                        : `Confirm ${entitiesSelected.size} entities`}
                    </RetroButton>
                  </div>
                </div>
              </RetroCardContent>
            </RetroCard>
          );
        }

        return null;
      })}

      {/* ==========================================
          EXTRACTION TRIGGER PANEL
          ========================================== */}
      {pendingExtractions.length > 0 && (
        <RetroCard>
          <RetroCardHeader>
            <GlowText as="h3" className="text-base">
              {pendingExtractions.length} Unstructured File
              {pendingExtractions.length !== 1 ? "s" : ""} Detected
            </GlowText>
            <p
              style={{
                fontSize: "0.7rem",
                color: "var(--theme-text-muted)",
                fontFamily: "var(--font-body)",
                marginTop: "0.25rem",
              }}
            >
              Text extraction required for clinical entity recognition
            </p>
          </RetroCardHeader>
          <RetroCardContent>
            <RetroTable>
              <RetroTableHeader>
                <RetroTableHead className="w-8">
                  <input
                    type="checkbox"
                    checked={
                      selectedForExtraction.size === pendingExtractions.length &&
                      pendingExtractions.length > 0
                    }
                    onChange={toggleSelectAllExtraction}
                    disabled={extractionTriggered}
                    style={{ accentColor: "var(--theme-amber)" }}
                  />
                </RetroTableHead>
                <RetroTableHead>File</RetroTableHead>
                <RetroTableHead>Type</RetroTableHead>
                <RetroTableHead>Status</RetroTableHead>
              </RetroTableHeader>
              <RetroTableBody>
                {pendingExtractions.map((file) => {
                  const ext = file.filename.split(".").pop()?.toLowerCase() || "";
                  const badgeColor =
                    ext === "pdf"
                      ? "var(--theme-terracotta)"
                      : ext === "rtf"
                        ? "var(--theme-sage)"
                        : "var(--theme-ochre)";
                  const currentStatus =
                    extractionStatuses[file.upload_id] || file.status;
                  return (
                    <RetroTableRow key={file.upload_id}>
                      <RetroTableCell>
                        <input
                          type="checkbox"
                          checked={selectedForExtraction.has(file.upload_id)}
                          onChange={() => toggleExtractionSelection(file.upload_id)}
                          disabled={extractionTriggered}
                          style={{ accentColor: "var(--theme-amber)" }}
                        />
                      </RetroTableCell>
                      <RetroTableCell>
                        <span
                          style={{
                            fontSize: "0.75rem",
                            fontFamily: "var(--font-body)",
                            color: "var(--theme-text)",
                            maxWidth: "250px",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                            display: "inline-block",
                          }}
                        >
                          {file.filename}
                        </span>
                      </RetroTableCell>
                      <RetroTableCell>
                        <span
                          style={{
                            fontSize: "0.6rem",
                            fontWeight: 700,
                            padding: "0.1rem 0.4rem",
                            borderRadius: "3px",
                            backgroundColor: badgeColor,
                            color: "var(--theme-bg-deep)",
                            fontFamily: "var(--font-body)",
                            textTransform: "uppercase",
                          }}
                        >
                          {ext}
                        </span>
                      </RetroTableCell>
                      <RetroTableCell>
                        <span
                          style={{
                            fontSize: "0.65rem",
                            fontWeight: 600,
                            padding: "0.15rem 0.5rem",
                            borderRadius: "4px",
                            fontFamily: "var(--font-body)",
                            backgroundColor:
                              currentStatus === "processing"
                                ? "var(--theme-amber)"
                                : currentStatus === "awaiting_confirmation"
                                  ? "var(--theme-sage)"
                                  : currentStatus === "failed"
                                    ? "var(--theme-terracotta)"
                                    : "var(--theme-text-muted)",
                            color: "var(--theme-bg-deep)",
                          }}
                        >
                          {currentStatus}
                        </span>
                      </RetroTableCell>
                    </RetroTableRow>
                  );
                })}
              </RetroTableBody>
            </RetroTable>

            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "0.75rem 0 0",
                borderTop: "1px solid var(--theme-border)",
                marginTop: "0.5rem",
              }}
            >
              <span
                style={{
                  fontSize: "0.7rem",
                  color: "var(--theme-text-muted)",
                  fontFamily: "var(--font-body)",
                }}
              >
                {selectedForExtraction.size} of {pendingExtractions.length} selected
              </span>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <RetroButton
                  variant="ghost"
                  onClick={handleDismissExtractionPanel}
                >
                  Do Later
                </RetroButton>
                <RetroButton
                  onClick={handleTriggerExtraction}
                  disabled={
                    selectedForExtraction.size === 0 || extractionTriggered
                  }
                >
                  {extractionTriggered
                    ? "Extracting..."
                    : `Extract ${selectedForExtraction.size} File${selectedForExtraction.size !== 1 ? "s" : ""}`}
                </RetroButton>
              </div>
            </div>
          </RetroCardContent>
        </RetroCard>
      )}

      {/* ==========================================
          UPLOAD HISTORY (COLLAPSIBLE)
          ========================================== */}
      <RetroCard>
        <div
          onClick={() => setHistoryOpen((prev) => !prev)}
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0.75rem 1rem",
            cursor: "pointer",
          }}
        >
          <span
            style={{
              fontSize: "0.8rem",
              fontWeight: 600,
              color: "var(--theme-text-dim)",
              fontFamily: "var(--font-body)",
            }}
          >
            Upload history
          </span>
          {historyOpen ? (
            <ChevronUp size={16} style={{ color: "var(--theme-text-muted)" }} />
          ) : (
            <ChevronDown size={16} style={{ color: "var(--theme-text-muted)" }} />
          )}
        </div>

        {historyOpen && (
          <RetroCardContent>
            {historyLoading ? (
              <RetroLoadingState text="Loading upload history" />
            ) : history.length === 0 ? (
              <p
                style={{
                  textAlign: "center",
                  padding: "1rem 0",
                  fontSize: "0.75rem",
                  color: "var(--theme-text-muted)",
                  fontFamily: "var(--font-body)",
                }}
              >
                No uploads yet
              </p>
            ) : (
              <RetroTable>
                <RetroTableHeader>
                  <RetroTableHead>Date</RetroTableHead>
                  <RetroTableHead>Source</RetroTableHead>
                  <RetroTableHead>Records</RetroTableHead>
                  <RetroTableHead>Status</RetroTableHead>
                  <RetroTableHead>Actions</RetroTableHead>
                </RetroTableHeader>
                <RetroTableBody>
                  {history.map((upload) => (
                    <RetroTableRow key={upload.id}>
                      <RetroTableCell>
                        <span
                          style={{
                            fontFamily: "VT323, monospace",
                            fontSize: "0.9rem",
                            color: "var(--theme-text-dim)",
                          }}
                        >
                          {upload.created_at
                            ? new Date(upload.created_at).toLocaleDateString()
                            : "--"}
                        </span>
                      </RetroTableCell>
                      <RetroTableCell>
                        <span
                          style={{
                            fontSize: "0.75rem",
                            color: "var(--theme-text)",
                            fontFamily: "var(--font-body)",
                            maxWidth: "200px",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                            display: "inline-block",
                          }}
                        >
                          {upload.original_filename}
                        </span>
                      </RetroTableCell>
                      <RetroTableCell>
                        <span
                          style={{
                            fontFamily: "VT323, monospace",
                            fontSize: "0.9rem",
                            color: "var(--theme-text-dim)",
                          }}
                        >
                          {upload.records_inserted ?? "--"}
                        </span>
                      </RetroTableCell>
                      <RetroTableCell>
                        <span
                          style={{
                            fontSize: "0.65rem",
                            fontWeight: 600,
                            padding: "0.15rem 0.5rem",
                            borderRadius: "4px",
                            fontFamily: "var(--font-body)",
                            backgroundColor:
                              upload.ingestion_status === "completed"
                                ? "var(--theme-sage)"
                                : upload.ingestion_status === "processing"
                                  ? "var(--theme-amber)"
                                  : upload.ingestion_status === "failed"
                                    ? "var(--theme-terracotta)"
                                    : upload.ingestion_status ===
                                        "awaiting_confirmation"
                                      ? "var(--record-procedure-text)"
                                      : upload.ingestion_status ===
                                          "pending_extraction"
                                        ? "var(--theme-ochre)"
                                        : "var(--theme-text-muted)",
                            color: "var(--theme-bg-deep)",
                          }}
                        >
                          {upload.ingestion_status}
                        </span>
                      </RetroTableCell>
                      <RetroTableCell>
                        {upload.ingestion_status === "pending_extraction" && (
                          <RetroButton
                            variant="ghost"
                            onClick={async (e: React.MouseEvent) => {
                              e.stopPropagation();
                              try {
                                await api.post<TriggerExtractionResponse>(
                                  "/upload/trigger-extraction",
                                  { upload_ids: [upload.id] }
                                );
                                setHistoryLoaded(false);
                              } catch {
                                // Silently fail
                              }
                            }}
                            style={{ fontSize: "0.65rem", padding: "0.15rem 0.4rem" }}
                          >
                            Extract
                          </RetroButton>
                        )}
                      </RetroTableCell>
                    </RetroTableRow>
                  ))}
                </RetroTableBody>
              </RetroTable>
            )}
          </RetroCardContent>
        )}
      </RetroCard>
    </div>
  );
}
