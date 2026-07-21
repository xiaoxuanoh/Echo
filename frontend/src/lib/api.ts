import type { ImageUploadResult, PdfUploadResult, Rotation } from "@/types/books";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

type ApiErrorBody = {
  error?: { message?: string };
};

async function parseResponse<T>(response: Response): Promise<T> {
  const body = (await response.json().catch(() => ({}))) as T & ApiErrorBody;
  if (!response.ok) {
    throw new Error(body.error?.message || "Echo could not complete the upload.");
  }
  return body;
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
