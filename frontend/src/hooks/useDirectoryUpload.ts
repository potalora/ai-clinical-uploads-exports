import { useCallback, useRef, useState } from "react";
import JSZip from "jszip";

const MAX_FILES = 10_000;
const MAX_TOTAL_BYTES = 5 * 1024 * 1024 * 1024; // 5 GB

const IGNORED_NAMES = new Set([".DS_Store", "Thumbs.db", "desktop.ini"]);
const IGNORED_PREFIXES = ["__MACOSX"];

function shouldSkip(name: string): boolean {
  return (
    IGNORED_NAMES.has(name) ||
    name.startsWith(".") ||
    IGNORED_PREFIXES.some((p) => name.startsWith(p))
  );
}

export interface FolderInfo {
  name: string;
  fileCount: number;
  totalSize: number;
}

interface UseDirectoryUploadOptions {
  onZipReady: (file: File, folderName: string, fileCount: number) => void;
  onError?: (message: string) => void;
}

export function useDirectoryUpload({
  onZipReady,
  onError,
}: UseDirectoryUploadOptions) {
  const folderInputRef = useRef<HTMLInputElement>(null);
  const [isZipping, setIsZipping] = useState(false);
  const [zipProgress, setZipProgress] = useState(0);
  const [folderInfo, setFolderInfo] = useState<FolderInfo | null>(null);

  const selectFolder = useCallback(() => {
    folderInputRef.current?.click();
  }, []);

  const createZipFromFiles = useCallback(
    async (files: File[], folderName: string) => {
      // Filter hidden/system files
      const filtered = files.filter((f) => {
        const pathParts = (f.webkitRelativePath || f.name).split("/");
        return !pathParts.some((part) => shouldSkip(part));
      });

      if (filtered.length === 0) {
        onError?.("No supported files found in the selected folder.");
        return;
      }

      if (filtered.length > MAX_FILES) {
        onError?.(
          `Folder contains ${filtered.length.toLocaleString()} files, exceeding the ${MAX_FILES.toLocaleString()} file limit.`
        );
        return;
      }

      const totalSize = filtered.reduce((sum, f) => sum + f.size, 0);
      if (totalSize > MAX_TOTAL_BYTES) {
        const sizeGB = (totalSize / (1024 * 1024 * 1024)).toFixed(1);
        onError?.(
          `Total folder size is ${sizeGB} GB, exceeding the 5 GB limit.`
        );
        return;
      }

      setFolderInfo({ name: folderName, fileCount: filtered.length, totalSize });
      setIsZipping(true);
      setZipProgress(0);

      try {
        const zip = new JSZip();

        for (const file of filtered) {
          const relativePath = file.webkitRelativePath || file.name;
          zip.file(relativePath, file, { compression: "STORE" });
        }

        const blob = await zip.generateAsync(
          { type: "blob", compression: "STORE" },
          (metadata) => {
            setZipProgress(metadata.percent);
          }
        );

        const zipFile = new File(
          [blob],
          `${folderName}.zip`,
          { type: "application/zip" }
        );

        onZipReady(zipFile, folderName, filtered.length);
      } catch {
        onError?.("Failed to create ZIP from folder.");
        setFolderInfo(null);
      } finally {
        setIsZipping(false);
        setZipProgress(0);
      }
    },
    [onZipReady, onError]
  );

  const handleFolderSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (!files || files.length === 0) return;

      const fileArray = Array.from(files);
      // Derive folder name from the first file's relative path
      const firstPath = fileArray[0]?.webkitRelativePath || "";
      const folderName = firstPath.split("/")[0] || "selected-folder";

      createZipFromFiles(fileArray, folderName);

      // Reset input so the same folder can be re-selected
      e.target.value = "";
    },
    [createZipFromFiles]
  );

  const clearFolderInfo = useCallback(() => {
    setFolderInfo(null);
  }, []);

  return {
    folderInputRef,
    isZipping,
    zipProgress,
    folderInfo,
    selectFolder,
    handleFolderSelect,
    createZipFromFiles,
    clearFolderInfo,
  };
}
