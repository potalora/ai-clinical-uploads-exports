const IGNORED_NAMES = new Set([".DS_Store", "Thumbs.db", "desktop.ini"]);
const IGNORED_PREFIXES = ["__MACOSX"];

function isIgnored(path: string): boolean {
  const parts = path.split("/");
  return parts.some(
    (part) =>
      IGNORED_NAMES.has(part) ||
      part.startsWith(".") ||
      IGNORED_PREFIXES.some((prefix) => part.startsWith(prefix))
  );
}

function readEntriesPromise(
  reader: FileSystemDirectoryReader
): Promise<FileSystemEntry[]> {
  return new Promise((resolve, reject) => {
    reader.readEntries(resolve, reject);
  });
}

async function readAllEntries(
  reader: FileSystemDirectoryReader
): Promise<FileSystemEntry[]> {
  const entries: FileSystemEntry[] = [];
  let batch: FileSystemEntry[];
  do {
    batch = await readEntriesPromise(reader);
    entries.push(...batch);
  } while (batch.length > 0);
  return entries;
}

function fileFromEntry(
  entry: FileSystemFileEntry,
  path: string
): Promise<File> {
  return new Promise((resolve, reject) => {
    entry.file((file) => {
      Object.defineProperty(file, "webkitRelativePath", {
        value: path,
        writable: false,
      });
      resolve(file);
    }, reject);
  });
}

async function traverseEntry(
  entry: FileSystemEntry,
  basePath: string
): Promise<File[]> {
  const path = basePath ? `${basePath}/${entry.name}` : entry.name;

  if (isIgnored(path)) return [];

  if (entry.isFile) {
    const file = await fileFromEntry(entry as FileSystemFileEntry, path);
    return [file];
  }

  if (entry.isDirectory) {
    const dirReader = (entry as FileSystemDirectoryEntry).createReader();
    const children = await readAllEntries(dirReader);
    const results: File[] = [];
    for (const child of children) {
      const childFiles = await traverseEntry(child, path);
      results.push(...childFiles);
    }
    return results;
  }

  return [];
}

/**
 * Recursively reads all files from dropped DataTransferItems that may include
 * directories. Returns null if no directories were found (caller should fall
 * through to default react-dropzone behavior).
 */
export async function getFilesFromDrop(
  dataTransfer: DataTransfer
): Promise<{ files: File[]; folderName: string } | null> {
  const items = Array.from(dataTransfer.items);
  let hasDirectory = false;
  const entries: FileSystemEntry[] = [];

  for (const item of items) {
    const entry = item.webkitGetAsEntry?.();
    if (entry) {
      if (entry.isDirectory) hasDirectory = true;
      entries.push(entry);
    }
  }

  if (!hasDirectory) return null;

  const folderName =
    entries.find((e) => e.isDirectory)?.name ?? "dropped-folder";

  const allFiles: File[] = [];
  for (const entry of entries) {
    const files = await traverseEntry(entry, "");
    allFiles.push(...files);
  }

  return { files: allFiles, folderName };
}
