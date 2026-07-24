import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BookUpload } from "@/components/upload/book-upload";

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
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("submits the confirmed order and rotation", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          book_id: "temporary-book-id",
          source_type: "images",
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
    render(<BookUpload />);
    fireEvent.click(
      screen.getByRole("button", { name: /^Upload Page Photos/ }),
    );

    const pageOne = new File(["one"], "page-one.png", { type: "image/png" });
    const pageTwo = new File(["two"], "page-two.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("Choose page photos"), {
      target: { files: [pageOne, pageTwo] },
    });

    fireEvent.click(screen.getAllByRole("button", { name: "Rotate right" })[0]);
    fireEvent.click(screen.getAllByRole("button", { name: "Later" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Prepare your book" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    const request = fetchMock.mock.calls[0][1];
    const body = request?.body as FormData;
    const filenames = body.getAll("files").map((entry) => (entry as File).name);

    expect(filenames).toEqual(["page-two.png", "page-one.png"]);
    expect(body.get("rotations")).toBe("[0,90]");
    expect(await screen.findByText("Your book pages are prepared")).toBeVisible();
    expect(screen.getByText("Page 1 · page-two.png")).toBeVisible();
    expect(screen.getAllByText("Image ready for text reading")).toHaveLength(2);
    expect(
      screen.getByRole("link", { name: "Continue preparing your book" }),
    ).toHaveAttribute("href", "/books/temporary-book-id");
  });

  it("submits a target library book when adding another recording", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          book_id: "new-recording-id",
          source_type: "pdf",
          total_pages: 1,
          original_filename: "chapter-two.pdf",
          classification: "text",
          pages: [],
          processing_status: "uploaded",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    render(<BookUpload libraryBookId="folder-id" libraryBookTitle="Ready book" />);

    const pdf = new File(["pdf"], "chapter-two.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText("Choose PDF"), {
      target: { files: [pdf] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Prepare your book" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    const body = fetchMock.mock.calls[0][1]?.body as FormData;
    expect(body.get("library_book_id")).toBe("folder-id");
    expect(await screen.findByText("Your new recording is prepared")).toBeVisible();
    expect(screen.getByText("Ready book")).toBeVisible();
  });
});
