export const MAX_PDF_SIZE_BYTES = 50 * 1024 * 1024;
export const MAX_IMAGE_SIZE_BYTES = 15 * 1024 * 1024;
export const MAX_IMAGE_UPLOAD_COUNT = 100;

const imageTypes = new Set(["image/jpeg", "image/png"]);
const imageExtensions = new Set(["jpg", "jpeg", "png"]);

function extension(filename: string): string {
  return filename.split(".").pop()?.toLowerCase() ?? "";
}

export function validatePdf(file: File): string | null {
  if (file.type !== "application/pdf" && extension(file.name) !== "pdf") {
    return "Please choose a PDF file.";
  }
  if (file.size === 0) return "The selected PDF is empty.";
  if (file.size > MAX_PDF_SIZE_BYTES) return "The PDF must be 50 MB or smaller.";
  return null;
}

export function validateNewImages(
  files: File[],
  existingCount: number,
): string | null {
  if (files.length === 0) return "Please choose at least one page image.";
  if (existingCount + files.length > MAX_IMAGE_UPLOAD_COUNT) {
    return `You can add up to ${MAX_IMAGE_UPLOAD_COUNT} page images.`;
  }
  for (const file of files) {
    if (!imageTypes.has(file.type) && !imageExtensions.has(extension(file.name))) {
      return `${file.name} is not a JPG or PNG image.`;
    }
    if (file.size === 0) return `${file.name} is empty.`;
    if (file.size > MAX_IMAGE_SIZE_BYTES) {
      return `${file.name} must be 15 MB or smaller.`;
    }
  }
  return null;
}
