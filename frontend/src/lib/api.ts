import type {
  AudioProcessingAccepted,
  DocumentAudio,
  DocumentDetail,
  DocumentLibrary,
  DocumentProcessingAccepted,
  ImageUploadResult,
  PdfUploadResult,
  Rotation,
} from "@/types/documents";
import type { ListeningLanguage } from "@/lib/listening-languages";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8001";

type ApiErrorBody = {
  error?: { message?: string };
};

async function parseResponse<T>(
  response: Response,
  fallbackMessage = "Echo could not complete the request.",
): Promise<T> {
  const body = (await response.json().catch(() => ({}))) as T & ApiErrorBody;
  if (!response.ok) {
    throw new Error(body.error?.message || fallbackMessage);
  }
  return body;
}

export async function getDocument(documentId: string): Promise<DocumentDetail> {
  return parseResponse<DocumentDetail>(
    await fetch(`${API_BASE_URL}/api/books/${documentId}`, { cache: "no-store" }),
    "Echo could not load this temporary document.",
  );
}

export async function getDocumentLibrary(): Promise<DocumentLibrary> {
  return parseResponse<DocumentLibrary>(
    await fetch(`${API_BASE_URL}/api/books`, { cache: "no-store" }),
    "Echo could not load your local library.",
  );
}

export async function renameDocumentFolder(
  folderId: string,
  title: string,
): Promise<void> {
  await parseResponse<{ message: string }>(
    await fetch(`${API_BASE_URL}/api/books/folders/${folderId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }),
    "Echo could not rename this upload.",
  );
}

export async function assignDocumentToFolder(
  documentId: string,
  folderId: string,
): Promise<void> {
  await parseResponse<{ message: string }>(
    await fetch(`${API_BASE_URL}/api/books/${documentId}/folder`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder_id: folderId }),
    }),
    "Echo could not save this recording to the folder.",
  );
}

export async function deleteDocumentFolder(folderId: string): Promise<void> {
  await parseResponse<{ message: string }>(
    await fetch(`${API_BASE_URL}/api/books/folders/${folderId}`, {
      method: "DELETE",
    }),
    "Echo could not remove this upload.",
  );
}

export async function deleteDocumentRecording(documentId: string): Promise<void> {
  await parseResponse<{ message: string }>(
    await fetch(`${API_BASE_URL}/api/books/${documentId}`, {
      method: "DELETE",
    }),
    "Echo could not remove this recording.",
  );
}

export async function renameDocumentRecording(
  documentId: string,
  title: string,
): Promise<void> {
  await parseResponse<{ message: string }>(
    await fetch(`${API_BASE_URL}/api/books/${documentId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }),
    "Echo could not rename this recording.",
  );
}

export async function startTextProcessing(
  documentId: string,
): Promise<DocumentProcessingAccepted> {
  return parseResponse<DocumentProcessingAccepted>(
    await fetch(`${API_BASE_URL}/api/books/${documentId}/process-text`, {
      method: "POST",
    }),
    "Echo could not start preparing the page text.",
  );
}

export async function retryPageText(
  documentId: string,
  pageNumber: number,
): Promise<DocumentProcessingAccepted> {
  return parseResponse<DocumentProcessingAccepted>(
    await fetch(
      `${API_BASE_URL}/api/books/${documentId}/pages/${pageNumber}/retry-text`,
      { method: "POST" },
    ),
    `Echo could not retry page ${pageNumber}.`,
  );
}

export async function getDocumentAudio(documentId: string): Promise<DocumentAudio> {
  return parseResponse<DocumentAudio>(
    await fetch(`${API_BASE_URL}/api/books/${documentId}/audio`, { cache: "no-store" }),
    "Echo could not load the listening audio.",
  );
}

export async function prepareDocumentAudio(
  documentId: string,
): Promise<AudioProcessingAccepted> {
  return parseResponse<AudioProcessingAccepted>(
    await fetch(`${API_BASE_URL}/api/books/${documentId}/prepare-audio`, {
      method: "POST",
    }),
    "Echo could not start creating listening audio.",
  );
}

export function audioFileUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return `${API_BASE_URL}${path}`;
}

export function recordingAudioDownloadUrl(documentId: string): string {
  return `${API_BASE_URL}/api/books/${documentId}/audio/download`;
}

export function preparedPageImageUrl(documentId: string, pageNumber: number): string {
  return `${API_BASE_URL}/api/books/${documentId}/pages/${pageNumber}/image`;
}

type UploadOptions = {
  libraryDocumentId?: string;
  targetLanguage?: ListeningLanguage;
};

export async function uploadPdf(
  file: File,
  options: UploadOptions = {},
): Promise<PdfUploadResult> {
  const formData = new FormData();
  formData.append("file", file);
  if (options.libraryDocumentId) {
    formData.append("library_book_id", options.libraryDocumentId);
  }
  if (options.targetLanguage) formData.append("target_language", options.targetLanguage);
  return parseResponse<PdfUploadResult>(
    await fetch(`${API_BASE_URL}/api/books/pdf`, {
      method: "POST",
      body: formData,
    }),
  );
}

export async function uploadImages(
  pages: { file: File; rotation: Rotation }[],
  options: UploadOptions = {},
): Promise<ImageUploadResult> {
  const formData = new FormData();
  for (const page of pages) formData.append("files", page.file);
  formData.append("rotations", JSON.stringify(pages.map((page) => page.rotation)));
  if (options.libraryDocumentId) {
    formData.append("library_book_id", options.libraryDocumentId);
  }
  if (options.targetLanguage) formData.append("target_language", options.targetLanguage);
  return parseResponse<ImageUploadResult>(
    await fetch(`${API_BASE_URL}/api/books/images`, {
      method: "POST",
      body: formData,
    }),
  );
}
