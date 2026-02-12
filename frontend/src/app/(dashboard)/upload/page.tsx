"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { api } from "@/lib/api";
import type { UploadResponse } from "@/types/api";

export default function UploadPage() {
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
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Upload Health Records</h1>
        <p className="text-muted-foreground">
          Import FHIR R4 JSON bundles or Epic EHI Tables exports (ZIP)
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Select File</CardTitle>
          <CardDescription>
            Drag and drop a file or click to browse. Supported formats: JSON (FHIR R4 bundles), ZIP (Epic EHI Tables exports).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div
            {...getRootProps()}
            className={`border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors ${
              isDragActive
                ? "border-primary bg-primary/5"
                : "border-muted-foreground/25 hover:border-primary/50"
            }`}
          >
            <input {...getInputProps()} />
            {isDragActive ? (
              <p className="text-primary font-medium">Drop the file here...</p>
            ) : (
              <div className="space-y-2">
                <p className="text-muted-foreground">
                  Drag and drop a file here, or click to select
                </p>
                <p className="text-xs text-muted-foreground">
                  JSON or ZIP files up to 500MB
                </p>
              </div>
            )}
          </div>

          {selectedFile && (
            <div className="flex items-center justify-between rounded-md border p-3">
              <div>
                <p className="text-sm font-medium">{selectedFile.name}</p>
                <p className="text-xs text-muted-foreground">
                  {(selectedFile.size / 1024).toFixed(1)} KB
                </p>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setSelectedFile(null)}
                >
                  Remove
                </Button>
                <Button
                  size="sm"
                  onClick={handleUpload}
                  disabled={uploading}
                >
                  {uploading ? "Uploading..." : "Upload"}
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {error && (
        <Alert variant="destructive">
          <AlertTitle>Upload Failed</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {result && (
        <Card>
          <CardHeader>
            <CardTitle>Upload Complete</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex justify-between py-1 border-b">
                <span className="text-sm text-muted-foreground">Status</span>
                <span className="text-sm font-medium">{result.status}</span>
              </div>
              <div className="flex justify-between py-1 border-b">
                <span className="text-sm text-muted-foreground">Records Inserted</span>
                <span className="text-sm font-medium">{result.records_inserted}</span>
              </div>
              {Array.isArray(result.errors) && result.errors.length > 0 && (
                <div className="pt-2">
                  <p className="text-sm font-medium text-destructive mb-2">
                    Errors ({result.errors.length})
                  </p>
                  <div className="max-h-48 overflow-auto space-y-1">
                    {result.errors.map((err, i) => (
                      <p key={i} className="text-xs text-muted-foreground font-mono bg-muted p-2 rounded">
                        {typeof err === "string" ? err : JSON.stringify(err)}
                      </p>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
