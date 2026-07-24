import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BookAudioPlayer } from "@/components/books/book-audio-player";


const textReadyAudio = {
  book_id: "book-id",
  title: "My book",
  target_language: "cantonese",
  tts_voice: "zh-HK-HiuMaanNeural",
  processing_status: "text_ready",
  processing_active: false,
  segments: [],
};

const readyAudio = {
  ...textReadyAudio,
  processing_status: "ready",
  segments: [
    {
      id: "segment-1",
      segment_number: 1,
      page_id: "page-1",
      page_number: 1,
      source_text: "第一段文字。",
      audio_url: "/api/books/book-id/audio/1/file",
      duration_seconds: 1.2,
      processing_status: "completed",
      error_message: null,
    },
    {
      id: "segment-2",
      segment_number: 2,
      page_id: "page-2",
      page_number: 2,
      source_text: "第二段文字。",
      audio_url: "/api/books/book-id/audio/2/file",
      duration_seconds: 1.2,
      processing_status: "completed",
      error_message: null,
    },
  ],
};

function jsonResponse(body: object, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function installLocalStorageStub() {
  const values = new Map<string, string>();
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
      clear: () => values.clear(),
    },
  });
}

describe("book audio player", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    installLocalStorageStub();
    window.localStorage.clear();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("starts mock audio creation from a text-ready book", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(jsonResponse(textReadyAudio))
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
      .mockResolvedValueOnce(jsonResponse(readyAudio));

    render(<BookAudioPlayer bookId="book-id" />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Create listening audio" }),
    );

    expect(await screen.findByText("2 audio parts ready")).toBeVisible();
    expect(screen.getByText("Page 1")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Part 1" })).toBeVisible();
    expect(fetchMock.mock.calls[1][0]).toContain("/prepare-audio");
  });

  it("moves between ready audio segments", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(readyAudio));
    const { container } = render(<BookAudioPlayer bookId="book-id" />);

    expect(await screen.findByRole("heading", { name: "Part 1" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Next part" }));

    expect(screen.getByRole("heading", { name: "Part 2" })).toBeVisible();
    expect(container.querySelector("audio")?.getAttribute("src")).toContain(
      "/api/books/book-id/audio/2/file",
    );
  });

  it("offers to continue interrupted audio creation", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        ...textReadyAudio,
        processing_status: "generating_audio",
      }),
    );

    render(<BookAudioPlayer bookId="book-id" />);

    expect(
      await screen.findByRole("button", { name: "Continue creating audio" }),
    ).toBeVisible();
    expect(
      screen.getByText("Audio creation appears to have stopped. Continue to resume it."),
    ).toBeVisible();
  });

  it("marks the book finished after the final segment ends", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(readyAudio));
    const { container } = render(<BookAudioPlayer bookId="book-id" />);

    expect(await screen.findByRole("heading", { name: "Part 1" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Next part" }));
    fireEvent.ended(container.querySelector("audio") as HTMLAudioElement);

    expect(screen.getByText("Finished this document.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Start over" })).toBeVisible();
    expect(
      JSON.parse(
        window.localStorage.getItem("echo:book-id:listening-progress") ?? "{}",
      ),
    ).toMatchObject({
      segmentNumber: 2,
      positionSeconds: 0,
      completed: true,
    });
  });
});
