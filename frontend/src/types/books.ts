export type PdfPageResult = {
  page_id: string;
  page_number: number;
  classification: "embedded_text" | "requires_ocr";
  original_filename: null;
  original_image_path: null;
  processed_image_path: string | null;
  extraction_method: "embedded_text" | "ocr";
  extracted_character_count: number;
  rotation_degrees: 0;
  processing_status: "pending" | "completed";
};

export type PdfUploadResult = {
  book_id: string;
  source_type: "pdf";
  total_pages: number;
  original_filename: string;
  classification: "text" | "scanned" | "mixed";
  pages: PdfPageResult[];
  processing_status: "uploaded";
};

export type ImagePageResult = {
  page_id: string;
  page_number: number;
  original_filename: string;
  original_image_path: string;
  processed_image_path: string;
  extraction_method: "ocr";
  extracted_character_count: 0;
  normalized_filename: string;
  rotation_degrees: 0 | 90 | 180 | 270;
  processing_status: "pending";
};

export type ImageUploadResult = {
  book_id: string;
  source_type: "images";
  total_pages: number;
  ordered_image_filenames: string[];
  pages: ImagePageResult[];
  processing_status: "uploaded";
};

export type UploadResult = PdfUploadResult | ImageUploadResult;
export type Rotation = 0 | 90 | 180 | 270;
