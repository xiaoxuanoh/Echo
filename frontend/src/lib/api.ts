import type {
  BookDetail,
  BookProcessingAccepted,
  ImageUploadResult,
  PdfUploadResult,
  Rotation,
} from "@/types/books";

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

export async function uploadPdf(file: File): Promise<PdfUploadResult> {
  const formData = new FormData();
  formData.append("file", file);
  return parseResponse<PdfUploadResult>(
    await fetch(`${API_BASE_URL}/api/books/pdf`, {
      method: "POST",
      body: formData,
    }),
  );
}

export async function uploadImages(
  pages: { file: File; rotation: Rotation }[],
): Promise<ImageUploadResult> {
  const formData = new FormData();
  for (const page of pages) formData.append("files", page.file);
  formData.append("rotations", JSON.stringify(pages.map((page) => page.rotation)));
  return parseResponse<ImageUploadResult>(
    await fetch(`${API_BASE_URL}/api/books/images`, {
      method: "POST",
      body: formData,
    }),
  );
}
