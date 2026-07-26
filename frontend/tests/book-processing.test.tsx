import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BookProcessing } from "@/components/books/book-processing";


const uploadedBook = {
  id: "book-id",
  title: "My book",
  original_filename: null,
  target_language: "cantonese",
  tts_voice: "zh-HK-HiuMaanNeural",
  source_type: "images",
  total_pages: 1,
  processing_status: "uploaded",
  error_message: null,
  completed_pages: 0,
  failed_pages: 0,
  audio_segment_count: 0,
  processing_active: false,
  pages: [
    {
      id: "page-id",
      page_number: 1,
      original_filename: "page.png",
      extraction_method: "ocr",
      extracted_text: "",
      extracted_character_count: 0,
      processing_status: "pending",
      error_message: null,
      updated_at: "2026-07-22T00:00:00Z",
    },
  ],
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-22T00:00:00Z",
};

const completedBook = {
  ...uploadedBook,
  processing_status: "text_ready",
  completed_pages: 1,
  pages: [
    {
      ...uploadedBook.pages[0],
      extracted_text: "這是準備好的文字。",
      extracted_character_count: 9,
      processing_status: "completed",
    },
  ],
};

const readyBook = {
  ...completedBook,
  processing_status: "ready",
  audio_segment_count: 1,
};

function jsonResponse(body: object, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("book text preparation", () => {
  beforeEach(() => vi.stubGlobal("fetch", vi.fn()));

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("creates listening audio through the full upload workflow", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(jsonResponse(uploadedBook))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            book_id: "book-id",
            processing_status: "running_ocr",
            message: "Echo has started reading the page text.",
          },
          202,
        ),
      )
      .mockResolvedValueOnce(jsonResponse(completedBook))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            book_id: "book-id",
            processing_status: "generating_audio",
            message: "Echo has started creating listening audio.",
          },
          202,
        ),
      )
      .mockResolvedValueOnce(jsonResponse(readyBook));

    render(<BookProcessing bookId="book-id" />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Create listening audio" }),
    );

    expect(await screen.findByText("Listening audio is ready.")).toBeVisible();
    expect(screen.getByText("1 of 1 pages ready")).toBeVisible();
    expect(screen.getByRole("link", { name: "Listen now" })).toBeVisible();
    expect(fetchMock).toHaveBeenCalledTimes(5);
    expect(fetchMock.mock.calls[1][0]).toContain("/process-text");
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: "POST" });
    expect(fetchMock.mock.calls[3][0]).toContain("/prepare-audio");
    expect(fetchMock.mock.calls[3][1]).toMatchObject({ method: "POST" });
  });

  it("starts audio directly from the prepared text state", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(jsonResponse(completedBook))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            book_id: "book-id",
            processing_status: "generating_audio",
            message: "Echo has started creating listening audio.",
          },
          202,
        ),
      )
      .mockResolvedValueOnce(jsonResponse(readyBook));

    render(<BookProcessing bookId="book-id" />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Create listening audio" }),
    );

    expect(await screen.findByText("Listening audio is ready.")).toBeVisible();
    expect(screen.getByRole("link", { name: "Listen now" })).toHaveAttribute(
      "href",
      "/books/book-id/listen",
    );
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1][0]).toContain("/prepare-audio");
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: "POST" });
  });

  it("retries a failed page", async () => {
    const failedBook = {
      ...uploadedBook,
      processing_status: "failed",
      error_message: "1 page still needs attention.",
      failed_pages: 1,
      pages: [
        {
          ...uploadedBook.pages[0],
          processing_status: "failed",
          error_message: "Echo could not read the text on this page.",
        },
      ],
    };
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(jsonResponse(failedBook))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            book_id: "book-id",
            processing_status: "running_ocr",
            message: "Echo is reading page 1 again.",
          },
          202,
        ),
      )
      .mockResolvedValueOnce(jsonResponse(completedBook));

    render(<BookProcessing bookId="book-id" />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Try this page again" }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(await screen.findByText("Page text ready")).toBeVisible();
    expect(fetchMock.mock.calls[1][0]).toContain("/pages/1/retry-text");
  });

  it("offers to continue an interrupted local job", async () => {
    const interruptedBook = {
      ...uploadedBook,
      processing_status: "running_ocr",
      processing_active: false,
    };
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(interruptedBook));

    render(<BookProcessing bookId="book-id" />);

    expect(
      await screen.findByRole("button", { name: "Create listening audio" }),
    ).toBeVisible();
    expect(
      screen.getByText(
        "Preparation appears to have stopped. Continue to resume from the first unfinished page.",
      ),
    ).toBeVisible();
  });
});
