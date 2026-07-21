export type PdfPageResult = {
  page_number: number;
  classification: "embedded_text" | "requires_ocr";
  extracted_character_count: number;
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
  page_number: number;
  original_filename: string;
  normalized_filename: string;
  rotation_degrees: 0 | 90 | 180 | 270;
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
