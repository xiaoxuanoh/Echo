import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DocumentUpload } from "@/components/upload/document-upload";

describe("page photo workflow", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn((file: File) => `blob:${file.name}`),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    vi.stubGlobal(
      "Image",
      class {
        naturalWidth = 1000;
        naturalHeight = 1400;
        onload: (() => void) | null = null;
        onerror: (() => void) | null = null;

        set src(_: string) {
          queueMicrotask(() => this.onload?.());
        }
      },
    );
    Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
      configurable: true,
      value: vi.fn(() => ({ drawImage: vi.fn() })),
    });
    Object.defineProperty(HTMLCanvasElement.prototype, "toBlob", {
      configurable: true,
      value: vi.fn((callback: BlobCallback) => callback(new Blob(["compressed"]))),
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("submits the selected pages and rotation", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          book_id: "temporary-document-id",
          source_type: "images",
          target_language: "cantonese",
          tts_voice: "zh-HK-HiuMaanNeural",
          total_pages: 2,
          ordered_image_filenames: ["page-two.png", "page-one.png"],
          pages: [
            {
              page_id: "page-id-1",
              page_number: 1,
              original_filename: "page-two.png",
              original_image_path: "originals/original-0001.png",
              processed_image_path: "pages/page-0001.png",
              extraction_method: "ocr",
              extracted_character_count: 0,
              normalized_filename: "page-0001.png",
              rotation_degrees: 0,
              processing_status: "pending",
            },
            {
              page_id: "page-id-2",
              page_number: 2,
              original_filename: "page-one.png",
              original_image_path: "originals/original-0002.png",
              processed_image_path: "pages/page-0002.png",
              extraction_method: "ocr",
              extracted_character_count: 0,
              normalized_filename: "page-0002.png",
              rotation_degrees: 90,
              processing_status: "pending",
            },
          ],
          processing_status: "uploaded",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    render(<DocumentUpload />);
    fireEvent.click(
      screen.getByRole("button", { name: /^Upload Page Photos/ }),
    );

    const pageOne = new File(["one"], "page-one.png", { type: "image/png" });
    const pageTwo = new File(["two"], "page-two.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("Choose page photos"), {
      target: { files: [pageOne, pageTwo] },
    });

    expect(screen.getByRole("button", { name: "Drag page 1 to reorder" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Earlier" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Later" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Rotate left" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Rotate right" })).not.toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Rotate" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Prepare your upload" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    const request = fetchMock.mock.calls[0][1];
    const body = request?.body as FormData;
    const filenames = body.getAll("files").map((entry) => (entry as File).name);

    expect(filenames).toEqual(["page-one.png", "page-two.png"]);
    expect(body.get("rotations")).toBe("[90,0]");
    expect(body.get("target_language")).toBe("cantonese");
    expect(await screen.findByText("Your document pages are prepared")).toBeVisible();
    expect(screen.getByText("Page 1 · page-two.png")).toBeVisible();
    expect(screen.getAllByText("Image ready for text reading")).toHaveLength(2);
    expect(screen.getByText("Preview pages before OCR")).toBeVisible();
    expect(screen.getByAltText("Prepared preview of page 1")).toHaveAttribute(
      "src",
      "http://localhost:8001/api/books/temporary-document-id/pages/1/image?v=0",
    );
    expect(
      screen.getByRole("link", { name: "Continue to page text" }),
    ).toHaveAttribute("href", "/books/temporary-document-id");
  });

  it("saves a manual crop for a prepared OCR page", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            book_id: "temporary-document-id",
            source_type: "images",
            target_language: "cantonese",
            tts_voice: "zh-HK-HiuMaanNeural",
            total_pages: 1,
            ordered_image_filenames: ["page-one.png"],
            pages: [
              {
                page_id: "page-id-1",
                page_number: 1,
                original_filename: "page-one.png",
                original_image_path: "originals/original-0001.png",
                processed_image_path: "pages/page-0001.png",
                extraction_method: "ocr",
                extracted_character_count: 0,
                normalized_filename: "page-0001.png",
                crop_left: null,
                crop_top: null,
                crop_right: null,
                crop_bottom: null,
                rotation_degrees: 0,
                processing_status: "pending",
              },
            ],
            processing_status: "uploaded",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            book_id: "temporary-document-id",
            page_id: "page-id-1",
            page_number: 1,
            crop_left: 0.2,
            crop_top: 0.1,
            crop_right: 0.8,
            crop_bottom: 0.9,
            processed_image_path: "pages/page-0001.png",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            book_id: "temporary-document-id",
            page_id: "page-id-1",
            page_number: 1,
            crop_left: 0.2,
            crop_top: 0.1,
            crop_right: 0.8,
            crop_bottom: 0.9,
            processed_image_path: "pages/page-0001.png",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );

    render(<DocumentUpload libraryDocumentId="folder-id" />);
    fireEvent.click(screen.getByRole("button", { name: /^Upload Page Photos/ }));
    fireEvent.change(screen.getByLabelText("Choose page photos"), {
      target: {
        files: [new File(["one"], "page-one.png", { type: "image/png" })],
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Prepare your upload" }));

    expect(await screen.findByText("Preview pages before OCR")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Crop" }));
    expect(screen.getByText("Drag the box to move it. Drag a corner to resize it.")).toBeVisible();
    expect(screen.queryByRole("slider")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save crop" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls[1][0]).toContain(
      "/api/books/temporary-document-id/pages/1/crop",
    );
    expect(fetchMock.mock.calls[1][1]).toMatchObject({
      method: "PUT",
      headers: { "Content-Type": "application/json" },
    });
    expect(JSON.parse(fetchMock.mock.calls[1][1]?.body as string)).toEqual({
      crop_left: 0,
      crop_top: 0,
      crop_right: 1,
      crop_bottom: 1,
    });
    expect(screen.getByAltText("Prepared preview of page 1")).toHaveAttribute(
      "src",
      "http://localhost:8001/api/books/temporary-document-id/pages/1/image?v=1",
    );

    fireEvent.click(screen.getByRole("button", { name: "Crop" }));
    fireEvent.click(screen.getByRole("button", { name: "Save crop" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(JSON.parse(fetchMock.mock.calls[2][1]?.body as string)).toEqual({
      crop_left: 0.2,
      crop_top: 0.1,
      crop_right: 0.8,
      crop_bottom: 0.9,
    });
  });

  it("submits a target library document when adding another recording", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          book_id: "new-recording-id",
          source_type: "pdf",
          target_language: "mandarin",
          tts_voice: "zh-CN-XiaoxiaoNeural",
          total_pages: 1,
          original_filename: "chapter-two.pdf",
          classification: "text",
          pages: [],
          processing_status: "uploaded",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    render(
      <DocumentUpload
        initialLanguage="mandarin"
        libraryDocumentId="folder-id"
        libraryDocumentTitle="Ready upload"
      />,
    );

    const pdf = new File(["pdf"], "chapter-two.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText("Choose PDF"), {
      target: { files: [pdf] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Rename" }));
    fireEvent.change(screen.getByLabelText("PDF name"), {
      target: { value: "chapter-two-renamed" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save name" }));
    fireEvent.click(screen.getByRole("button", { name: "Prepare your upload" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    const body = fetchMock.mock.calls[0][1]?.body as FormData;
    expect((body.get("file") as File).name).toBe("chapter-two-renamed.pdf");
    expect(body.get("library_book_id")).toBe("folder-id");
    expect(body.get("target_language")).toBe("mandarin");
    expect(await screen.findByText("Your new recording is prepared")).toBeVisible();
    expect(screen.getByText("Ready upload")).toBeVisible();
  });

  it("assigns a new upload to an existing folder from the modal", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            book_id: "new-recording-id",
            source_type: "pdf",
            target_language: "cantonese",
            tts_voice: "zh-HK-HiuMaanNeural",
            total_pages: 1,
            original_filename: "chapter.pdf",
            classification: "text",
            pages: [],
            processing_status: "uploaded",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            folders: [
              {
                id: "new-recording-id",
                title: "chapter",
                recording_count: 1,
                total_pages: 1,
                processing_status: "uploaded",
                processing_active: false,
                target_languages: [],
                latest_recording_at: "2026-07-25T00:00:00Z",
                recordings: [],
              },
              {
                id: "existing-folder-id",
                title: "Echo test",
                recording_count: 2,
                total_pages: 3,
                processing_status: "ready",
                processing_active: false,
                target_languages: [],
                latest_recording_at: "2026-07-24T00:00:00Z",
                recordings: [],
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ message: "Saved" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );

    render(<DocumentUpload />);
    fireEvent.change(screen.getByLabelText("Choose PDF"), {
      target: { files: [new File(["pdf"], "chapter.pdf", { type: "application/pdf" })] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Prepare your upload" }));

    expect(await screen.findByText("Where should we save this upload?")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Save to existing folder" }));
    expect(await screen.findByRole("button", { name: "Echo test" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Echo test" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(fetchMock.mock.calls[2][0]).toContain("/api/books/new-recording-id/folder");
    expect(fetchMock.mock.calls[2][1]).toMatchObject({ method: "PATCH" });
    expect(JSON.parse(fetchMock.mock.calls[2][1]?.body as string)).toEqual({
      folder_id: "existing-folder-id",
    });
  });

  it("creates a new folder from the upload destination modal", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          book_id: "new-recording-id",
          source_type: "pdf",
          target_language: "cantonese",
          tts_voice: "zh-HK-HiuMaanNeural",
          total_pages: 1,
          original_filename: "chapter.pdf",
          classification: "text",
          pages: [],
          processing_status: "uploaded",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    render(<DocumentUpload />);
    fireEvent.change(screen.getByLabelText("Choose PDF"), {
      target: { files: [new File(["pdf"], "chapter.pdf", { type: "application/pdf" })] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Prepare your upload" }));
    fireEvent.click(await screen.findByRole("button", { name: "Create a new folder" }));
    fireEvent.change(screen.getByLabelText("Folder name"), {
      target: { value: "Echo test" },
    });

    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ message: "Renamed" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Create and continue" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls[1][0]).toContain("/api/books/folders/new-recording-id");
    expect(JSON.parse(fetchMock.mock.calls[1][1]?.body as string)).toEqual({
      title: "Echo test",
    });
  });
});
