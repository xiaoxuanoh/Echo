import type {
  AudioProcessingAccepted,
  BookAudio,
  BookDetail,
  BookLibrary,
  BookProcessingAccepted,
  ImageUploadResult,
  PdfUploadResult,
  Rotation,
} from "@/types/books";
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

export async function getBook(bookId: string): Promise<BookDetail> {
  return parseResponse<BookDetail>(
    await fetch(`${API_BASE_URL}/api/books/${bookId}`, { cache: "no-store" }),
    "Echo could not load this temporary book.",
  );
}

export async function getBookLibrary(): Promise<BookLibrary> {
  return parseResponse<BookLibrary>(
    await fetch(`${API_BASE_URL}/api/books`, { cache: "no-store" }),
    "Echo could not load your local library.",
  );
}

export async function renameBookFolder(
  folderId: string,
  title: string,
): Promise<void> {
  await parseResponse<{ message: string }>(
    await fetch(`${API_BASE_URL}/api/books/folders/${folderId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }),
    "Echo could not rename this book.",
  );
}

export async function deleteBookFolder(folderId: string): Promise<void> {
  await parseResponse<{ message: string }>(
    await fetch(`${API_BASE_URL}/api/books/folders/${folderId}`, {
      method: "DELETE",
    }),
    "Echo could not remove this book.",
  );
}

export async function deleteBookRecording(bookId: string): Promise<void> {
  await parseResponse<{ message: string }>(
    await fetch(`${API_BASE_URL}/api/books/${bookId}`, {
      method: "DELETE",
    }),
    "Echo could not remove this recording.",
  );
}

export async function renameBookRecording(
  bookId: string,
  title: string,
): Promise<void> {
  await parseResponse<{ message: string }>(
    await fetch(`${API_BASE_URL}/api/books/${bookId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }),
    "Echo could not rename this recording.",
  );
}

export async function startTextProcessing(
  bookId: string,
): Promise<BookProcessingAccepted> {
  return parseResponse<BookProcessingAccepted>(
    await fetch(`${API_BASE_URL}/api/books/${bookId}/process-text`, {
      method: "POST",
    }),
    "Echo could not start preparing the page text.",
  );
}

export async function retryPageText(
  bookId: string,
  pageNumber: number,
): Promise<BookProcessingAccepted> {
  return parseResponse<BookProcessingAccepted>(
    await fetch(
      `${API_BASE_URL}/api/books/${bookId}/pages/${pageNumber}/retry-text`,
      { method: "POST" },
    ),
    `Echo could not retry page ${pageNumber}.`,
  );
}

export async function getBookAudio(bookId: string): Promise<BookAudio> {
  return parseResponse<BookAudio>(
    await fetch(`${API_BASE_URL}/api/books/${bookId}/audio`, { cache: "no-store" }),
    "Echo could not load the listening audio.",
  );
}

export async function prepareBookAudio(
  bookId: string,
): Promise<AudioProcessingAccepted> {
  return parseResponse<AudioProcessingAccepted>(
    await fetch(`${API_BASE_URL}/api/books/${bookId}/prepare-audio`, {
      method: "POST",
    }),
    "Echo could not start creating listening audio.",
  );
}

export function audioFileUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return `${API_BASE_URL}${path}`;
}

type UploadOptions = {
  libraryBookId?: string;
  targetLanguage?: ListeningLanguage;
};

export async function uploadPdf(
  file: File,
  options: UploadOptions = {},
): Promise<PdfUploadResult> {
  const formData = new FormData();
  formData.append("file", file);
  if (options.libraryBookId) formData.append("library_book_id", options.libraryBookId);
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
  if (options.libraryBookId) formData.append("library_book_id", options.libraryBookId);
  if (options.targetLanguage) formData.append("target_language", options.targetLanguage);
  return parseResponse<ImageUploadResult>(
    await fetch(`${API_BASE_URL}/api/books/images`, {
      method: "POST",
      body: formData,
    }),
  );
}
