import type {
  AudioProcessingAccepted,
  DocumentAudio,
  DocumentDetail,
  DocumentLibrary,
  DocumentProcessingAccepted,
  ImageUploadResult,
  PageCrop,
  PageCropResult,
  PdfUploadResult,
  Rotation,
} from "@/types/documents";
import type { ListeningLanguage } from "@/lib/listening-languages";
import { getSupabaseBrowserClient } from "@/lib/supabase/browser";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8001";
const IMAGE_UPLOAD_MAX_SIDE = 1800;
const IMAGE_UPLOAD_JPEG_QUALITY = 0.78;

type ApiErrorBody = {
  error?: { message?: string };
};

async function authHeaders(): Promise<Record<string, string>> {
  const supabase = getSupabaseBrowserClient();
  if (!supabase) return {};
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function echoFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  const headers =
    init.headers instanceof Headers || Array.isArray(init.headers)
      ? Object.fromEntries(new Headers(init.headers).entries())
      : { ...(init.headers ?? {}) };
  for (const [key, value] of Object.entries(await authHeaders())) {
    headers[key] = value;
  }
  return fetch(input, { ...init, headers });
}

export async function currentAccessToken(): Promise<string | null> {
  const supabase = getSupabaseBrowserClient();
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

function urlWithAccessToken(url: string, accessToken?: string | null): string {
  if (!accessToken) return url;
  const nextUrl = new URL(url, API_BASE_URL);
  nextUrl.searchParams.set("access_token", accessToken);
  return nextUrl.toString();
}

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
    await echoFetch(`${API_BASE_URL}/api/books/${documentId}`, { cache: "no-store" }),
    "Echo could not load this temporary document.",
  );
}

export async function getDocumentLibrary(): Promise<DocumentLibrary> {
  return parseResponse<DocumentLibrary>(
    await echoFetch(`${API_BASE_URL}/api/books`, { cache: "no-store" }),
    "Echo could not load your local library.",
  );
}

export async function renameDocumentFolder(
  folderId: string,
  title: string,
): Promise<void> {
  await parseResponse<{ message: string }>(
    await echoFetch(`${API_BASE_URL}/api/books/folders/${folderId}`, {
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
    await echoFetch(`${API_BASE_URL}/api/books/${documentId}/folder`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder_id: folderId }),
    }),
    "Echo could not save this recording to the folder.",
  );
}

export async function deleteDocumentFolder(folderId: string): Promise<void> {
  await parseResponse<{ message: string }>(
    await echoFetch(`${API_BASE_URL}/api/books/folders/${folderId}`, {
      method: "DELETE",
    }),
    "Echo could not remove this upload.",
  );
}

export async function deleteDocumentRecording(documentId: string): Promise<void> {
  await parseResponse<{ message: string }>(
    await echoFetch(`${API_BASE_URL}/api/books/${documentId}`, {
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
    await echoFetch(`${API_BASE_URL}/api/books/${documentId}`, {
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
    await echoFetch(`${API_BASE_URL}/api/books/${documentId}/process-text`, {
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
    await echoFetch(
      `${API_BASE_URL}/api/books/${documentId}/pages/${pageNumber}/retry-text`,
      { method: "POST" },
    ),
    `Echo could not retry page ${pageNumber}.`,
  );
}

export async function updatePageText(
  documentId: string,
  pageNumber: number,
  text: string,
): Promise<DocumentDetail> {
  return parseResponse<DocumentDetail>(
    await echoFetch(`${API_BASE_URL}/api/books/${documentId}/pages/${pageNumber}/text`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    }),
    `Echo could not save page ${pageNumber} text.`,
  );
}

export async function getDocumentAudio(documentId: string): Promise<DocumentAudio> {
  return parseResponse<DocumentAudio>(
    await echoFetch(`${API_BASE_URL}/api/books/${documentId}/audio`, { cache: "no-store" }),
    "Echo could not load the listening audio.",
  );
}

export async function prepareDocumentAudio(
  documentId: string,
): Promise<AudioProcessingAccepted> {
  return parseResponse<AudioProcessingAccepted>(
    await echoFetch(`${API_BASE_URL}/api/books/${documentId}/prepare-audio`, {
      method: "POST",
    }),
    "Echo could not start creating listening audio.",
  );
}

export function audioFileUrl(path: string, accessToken?: string | null): string {
  const url = path.startsWith("http://") || path.startsWith("https://")
    ? path
    : `${API_BASE_URL}${path}`;
  return urlWithAccessToken(url, accessToken);
}

export function recordingAudioDownloadUrl(
  documentId: string,
  accessToken?: string | null,
): string {
  return urlWithAccessToken(
    `${API_BASE_URL}/api/books/${documentId}/audio/download`,
    accessToken,
  );
}

export function folderAudioDownloadUrl(
  folderId: string,
  accessToken?: string | null,
): string {
  return urlWithAccessToken(
    `${API_BASE_URL}/api/books/folders/${folderId}/audio/download`,
    accessToken,
  );
}

export function preparedPageImageUrl(
  documentId: string,
  pageNumber: number,
  accessToken?: string | null,
): string {
  return urlWithAccessToken(
    `${API_BASE_URL}/api/books/${documentId}/pages/${pageNumber}/image`,
    accessToken,
  );
}

export async function updatePreparedPageCrop(
  documentId: string,
  pageNumber: number,
  crop: PageCrop,
): Promise<PageCropResult> {
  return parseResponse<PageCropResult>(
    await echoFetch(`${API_BASE_URL}/api/books/${documentId}/pages/${pageNumber}/crop`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(crop),
    }),
    `Echo could not save the crop for page ${pageNumber}.`,
  );
}

export async function rotatePreparedPage(
  documentId: string,
  pageNumber: number,
  direction: "left" | "right",
): Promise<DocumentDetail> {
  return parseResponse<DocumentDetail>(
    await echoFetch(
      `${API_BASE_URL}/api/books/${documentId}/pages/${pageNumber}/rotation`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ direction }),
      },
    ),
    `Echo could not rotate page ${pageNumber}.`,
  );
}

export async function reorderPreparedPages(
  documentId: string,
  pageIds: string[],
): Promise<DocumentDetail> {
  return parseResponse<DocumentDetail>(
    await echoFetch(`${API_BASE_URL}/api/books/${documentId}/pages/order`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ page_ids: pageIds }),
    }),
    "Echo could not rearrange these pages.",
  );
}

export async function removePreparedPage(
  documentId: string,
  pageNumber: number,
): Promise<DocumentDetail> {
  return parseResponse<DocumentDetail>(
    await echoFetch(`${API_BASE_URL}/api/books/${documentId}/pages/${pageNumber}`, {
      method: "DELETE",
    }),
    `Echo could not remove page ${pageNumber}.`,
  );
}

type UploadOptions = {
  libraryDocumentId?: string;
  targetLanguage?: ListeningLanguage;
};

async function compressedPageImage(file: File): Promise<File> {
  if (!file.type.startsWith("image/")) return file;

  const imageUrl = URL.createObjectURL(file);
  try {
    const image = new Image();
    const loaded = new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error("Echo could not prepare this page photo."));
    });
    image.src = imageUrl;
    await loaded;

    const scale = Math.min(
      1,
      IMAGE_UPLOAD_MAX_SIDE / Math.max(image.naturalWidth, image.naturalHeight),
    );
    const width = Math.max(1, Math.round(image.naturalWidth * scale));
    const height = Math.max(1, Math.round(image.naturalHeight * scale));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    if (!context) return file;
    context.drawImage(image, 0, 0, width, height);

    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", IMAGE_UPLOAD_JPEG_QUALITY),
    );
    if (!blob || blob.size >= file.size) return file;

    return new File([blob], imageUploadFilename(file.name), {
      type: "image/jpeg",
      lastModified: file.lastModified,
    });
  } catch {
    return file;
  } finally {
    URL.revokeObjectURL(imageUrl);
  }
}

function imageUploadFilename(filename: string): string {
  const stem = filename.replace(/\.[^/.]+$/, "") || "page";
  return `${stem}.jpg`;
}

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
    await echoFetch(`${API_BASE_URL}/api/books/pdf`, {
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
  for (const page of pages) {
    formData.append("files", await compressedPageImage(page.file));
  }
  formData.append("rotations", JSON.stringify(pages.map((page) => page.rotation)));
  if (options.libraryDocumentId) {
    formData.append("library_book_id", options.libraryDocumentId);
  }
  if (options.targetLanguage) formData.append("target_language", options.targetLanguage);
  return parseResponse<ImageUploadResult>(
    await echoFetch(`${API_BASE_URL}/api/books/images`, {
      method: "POST",
      body: formData,
    }),
  );
}
