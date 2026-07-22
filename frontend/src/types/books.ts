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

export type BookProcessingStatus =
  | "uploaded"
  | "normalizing_pages"
  | "inspecting"
  | "extracting_text"
  | "running_ocr"
  | "text_ready"
  | "generating_audio"
  | "ready"
  | "failed";

export type PageProcessingStatus =
  | "pending"
  | "normalizing"
  | "extracting"
  | "running_ocr"
  | "completed"
  | "failed";

export type BookPageDetail = {
  id: string;
  page_number: number;
  original_filename: string | null;
  extraction_method: "pending" | "embedded_text" | "ocr";
  extracted_text: string;
  extracted_character_count: number;
  processing_status: PageProcessingStatus;
  error_message: string | null;
  updated_at: string;
};

export type BookDetail = {
  id: string;
  title: string;
  original_filename: string | null;
  source_type: "pdf" | "images";
  total_pages: number;
  processing_status: BookProcessingStatus;
  error_message: string | null;
  completed_pages: number;
  failed_pages: number;
  audio_segment_count: number;
  processing_active: boolean;
  pages: BookPageDetail[];
  created_at: string;
  updated_at: string;
};

export type BookProcessingAccepted = {
  book_id: string;
  processing_status: "extracting_text" | "running_ocr";
  message: string;
};

export type AudioSegment = {
  id: string;
  segment_number: number;
  page_id: string | null;
  page_number: number | null;
  source_text: string;
  audio_url: string | null;
  duration_seconds: number | null;
  processing_status: "pending" | "generating" | "completed" | "failed";
  error_message: string | null;
};

export type BookAudio = {
  book_id: string;
  title: string;
  processing_status: BookProcessingStatus;
  processing_active: boolean;
  segments: AudioSegment[];
};

export type AudioProcessingAccepted = {
  book_id: string;
  processing_status: "generating_audio";
  message: string;
};
