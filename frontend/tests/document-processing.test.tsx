import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DocumentProcessing } from "@/components/documents/document-processing";

const pushMock = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
  }),
}));

const uploadedDocument = {
  id: "document-id",
  title: "My document",
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
      crop_left: null,
      crop_top: null,
      crop_right: null,
      crop_bottom: null,
      rotation_degrees: 0,
      processing_status: "pending",
      error_message: null,
      warning_messages: [],
      updated_at: "2026-07-22T00:00:00Z",
    },
  ],
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-22T00:00:00Z",
};

const completedDocument = {
  ...uploadedDocument,
  processing_status: "text_ready",
  completed_pages: 1,
  pages: [
    {
      ...uploadedDocument.pages[0],
      extracted_text: "這是準備好的文字。",
      extracted_character_count: 9,
      processing_status: "completed",
    },
  ],
};

const readyDocument = {
  ...completedDocument,
  processing_status: "ready",
  audio_segment_count: 1,
};

const activeAudioDocument = {
  ...completedDocument,
  processing_status: "generating_audio",
  processing_active: true,
  audio_segment_count: 1,
};

function jsonResponse(body: object, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("document text preparation", () => {
  beforeEach(() => {
    pushMock.mockReset();
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("previews prepared OCR pages before text preparation starts", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(jsonResponse(uploadedDocument))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            book_id: "document-id",
            processing_status: "running_ocr",
            message: "Echo has started reading the page text.",
          },
          202,
        ),
      )
      .mockResolvedValueOnce(jsonResponse(completedDocument))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            book_id: "document-id",
            processing_status: "generating_audio",
            message: "Echo has started creating listening audio.",
          },
          202,
        ),
      )
      .mockResolvedValueOnce(jsonResponse(readyDocument));

    render(<DocumentProcessing documentId="document-id" />);

    expect(await screen.findByText("Review pages before text reading")).toBeVisible();
    expect(screen.getByAltText("Prepared preview of page 1")).toHaveAttribute(
      "src",
      "http://localhost:8001/api/books/document-id/pages/1/image?v=0",
    );
    expect(screen.getByRole("button", { name: "Rotate left" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Rotate right" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Crop" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Drag page 1 to reorder" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Remove page" })).toBeDisabled();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Start reading page text" }));

    await waitFor(() => expect(fetchMock.mock.calls[1][0]).toContain("/process-text"));
    expect(
      await screen.findByText(
        "All page text is prepared. Select Listen now to create listening audio.",
      ),
    ).toBeVisible();

    fireEvent.click(
      screen.getByRole("button", { name: "Listen now" }),
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

  it("edits prepared OCR pages before text preparation starts", async () => {
    const fetchMock = vi.mocked(fetch);
    const twoPageDocument = {
      ...uploadedDocument,
      total_pages: 2,
      pages: [
        uploadedDocument.pages[0],
        {
          ...uploadedDocument.pages[0],
          id: "page-id-2",
          page_number: 2,
          original_filename: "page-2.png",
        },
      ],
    };
    const rotatedDocument = {
      ...twoPageDocument,
      pages: [
        { ...twoPageDocument.pages[0], rotation_degrees: 90 },
        twoPageDocument.pages[1],
      ],
    };
    const removedDocument = {
      ...twoPageDocument,
      total_pages: 1,
      pages: [twoPageDocument.pages[1]],
    };

    fetchMock
      .mockResolvedValueOnce(jsonResponse(twoPageDocument))
      .mockResolvedValueOnce(jsonResponse(rotatedDocument))
      .mockResolvedValueOnce(jsonResponse(removedDocument));
    const confirmMock = vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<DocumentProcessing documentId="document-id" />);

    expect(await screen.findByText("Review pages before text reading")).toBeVisible();
    fireEvent.click(screen.getAllByRole("button", { name: "Rotate right" })[0]);
    expect(screen.getByRole("button", { name: "Drag page 1 to reorder" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Move later" })).not.toBeInTheDocument();

    await waitFor(() =>
      expect(fetchMock.mock.calls[1][0]).toContain("/pages/1/rotation"),
    );
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: "PUT" });
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({
      direction: "right",
    });

    fireEvent.click(screen.getAllByRole("button", { name: "Remove page" })[0]);

    await waitFor(() => expect(fetchMock.mock.calls[2][0]).toContain("/pages/1"));
    expect(fetchMock.mock.calls[2][1]).toMatchObject({ method: "DELETE" });
    expect(confirmMock).toHaveBeenCalledWith("Remove page 1 from this upload?");
  });

  it("restarts the review by removing the upload and returning to upload", async () => {
    const confirmMock = vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(jsonResponse(uploadedDocument))
      .mockResolvedValueOnce(jsonResponse({ message: "removed" }));

    render(<DocumentProcessing documentId="document-id" />);

    fireEvent.click(await screen.findByRole("button", { name: "Restart" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(confirmMock).toHaveBeenCalledWith(
      'Restart this upload? Echo will remove "My document" from your library.',
    );
    expect(fetchMock.mock.calls[1][0]).toBe("http://localhost:8001/api/books/document-id");
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: "DELETE" });
    expect(pushMock).toHaveBeenCalledWith("/books/new");
  });

  it("starts audio directly from the prepared text state", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(jsonResponse(completedDocument))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            book_id: "document-id",
            processing_status: "generating_audio",
            message: "Echo has started creating listening audio.",
          },
          202,
        ),
      )
      .mockResolvedValueOnce(jsonResponse(readyDocument));

    render(<DocumentProcessing documentId="document-id" />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Listen now" }),
    );

    expect(await screen.findByText("Listening audio is ready.")).toBeVisible();
    expect(screen.getByRole("link", { name: "Listen now" })).toHaveAttribute(
      "href",
      "/books/document-id/listen",
    );
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1][0]).toContain("/prepare-audio");
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: "POST" });
  });

  it("keeps listen now disabled while OCR is active", async () => {
    const processingDocument = {
      ...uploadedDocument,
      processing_status: "running_ocr",
      processing_active: true,
    };
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(processingDocument));

    render(<DocumentProcessing documentId="document-id" />);

    expect(await screen.findByRole("button", { name: "Listen now" })).toBeDisabled();
    expect(
      screen.getByText(
        "Echo is reading your pages first. Listen now will unlock when the text is ready.",
      ),
    ).toBeVisible();
  });

  it("retries a failed page", async () => {
    const failedDocument = {
      ...uploadedDocument,
      processing_status: "failed",
      error_message: "1 page still needs attention.",
      failed_pages: 1,
      pages: [
        {
          ...uploadedDocument.pages[0],
          processing_status: "failed",
          error_message: "Echo could not read the text on this page.",
        },
      ],
    };
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(jsonResponse(failedDocument))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            book_id: "document-id",
            processing_status: "running_ocr",
            message: "Echo is reading page 1 again.",
          },
          202,
        ),
      )
      .mockResolvedValueOnce(jsonResponse(completedDocument));

    render(<DocumentProcessing documentId="document-id" />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Try this page again" }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(await screen.findByText("Page text ready")).toBeVisible();
    expect(fetchMock.mock.calls[1][0]).toContain("/pages/1/retry-text");
  });

  it("saves manual text for a failed OCR page", async () => {
    const failedDocument = {
      ...uploadedDocument,
      processing_status: "failed",
      error_message: "1 page still needs attention.",
      failed_pages: 1,
      pages: [
        {
          ...uploadedDocument.pages[0],
          processing_status: "failed",
          error_message: "Echo could not read the text on this page.",
        },
      ],
    };
    const manuallyCompletedDocument = {
      ...completedDocument,
      pages: [
        {
          ...completedDocument.pages[0],
          extracted_text: "讀畢本章，當你知道如何謹慎且適當地使用時。",
          extracted_character_count: 22,
        },
      ],
    };
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(jsonResponse(failedDocument))
      .mockResolvedValueOnce(jsonResponse(manuallyCompletedDocument));

    render(<DocumentProcessing documentId="document-id" />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Enter page text manually" }),
    );
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "讀畢本章，當你知道如何謹慎且適當地使用時。" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save page text" }));

    expect(
      await screen.findByText(
        "All page text is prepared. Select Listen now to create listening audio.",
      ),
    ).toBeVisible();
    expect(fetchMock.mock.calls[1][0]).toContain("/pages/1/text");
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: "PATCH" });
  });

  it("offers to continue an interrupted local job", async () => {
    const interruptedDocument = {
      ...uploadedDocument,
      processing_status: "running_ocr",
      processing_active: false,
    };
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(interruptedDocument));

    render(<DocumentProcessing documentId="document-id" />);

    expect(
      await screen.findByRole("button", { name: "Listen now" }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: "Resume reading pages" })).toBeVisible();
    expect(
      screen.getByText(
        "Preparation appears to have stopped. Resume reading from the first unfinished page.",
      ),
    ).toBeVisible();
  });

  it("offers to recover failed audio preparation after page text is ready", async () => {
    const failedAudioDocument = {
      ...completedDocument,
      processing_status: "failed",
      error_message: "Audio preparation stopped before it finished.",
      audio_segment_count: 1,
      failed_pages: 0,
    };
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(jsonResponse(failedAudioDocument))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            book_id: "document-id",
            processing_status: "generating_audio",
            message: "Echo has started creating listening audio.",
          },
          202,
        ),
      )
      .mockResolvedValueOnce(jsonResponse(readyDocument));

    render(<DocumentProcessing documentId="document-id" />);

    expect(
      await screen.findByRole("button", { name: "Resume audio preparation" }),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Resume audio preparation" }));

    expect(await screen.findByText("Listening audio is ready.")).toBeVisible();
    expect(fetchMock.mock.calls[1][0]).toContain("/prepare-audio");
  });

  it("keeps the progress view during one transient audio polling error", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(jsonResponse(activeAudioDocument))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            error: {
              message: "Echo could not reach the library database right now.",
            },
          },
          503,
        ),
      );

    render(<DocumentProcessing documentId="document-id" />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(screen.getByText("Creating the audio")).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
