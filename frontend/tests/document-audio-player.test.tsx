import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DocumentAudioPlayer } from "@/components/documents/document-audio-player";


const authSessionMock = vi.hoisted(() => vi.fn());

vi.mock("@/components/auth/use-auth-session", () => ({
  useAuthSession: () => authSessionMock(),
}));

const textReadyAudio = {
  book_id: "document-id",
  library_book_id: "folder-id",
  title: "My document",
  recording_title: null,
  original_filename: "my-document.pdf",
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
      audio_url: "/api/books/document-id/audio/1/file",
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
      audio_url: "/api/books/document-id/audio/2/file",
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

describe("document audio player", () => {
  beforeEach(() => {
    authSessionMock.mockReturnValue({
      isConfigured: false,
      isLoadingSession: false,
      isSignedIn: false,
      authEvent: null,
      session: null,
      setSession: vi.fn(),
      supabase: null,
    });
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

  it("asks signed-out users to sign in before fetching protected listening data", () => {
    authSessionMock.mockReturnValue({
      isConfigured: true,
      isLoadingSession: false,
      isSignedIn: false,
      authEvent: null,
      session: null,
      setSession: vi.fn(),
      supabase: {},
    });

    render(<DocumentAudioPlayer documentId="document-id" />);

    expect(screen.getByRole("heading", { name: "Sign in to listen" })).toBeVisible();
    expect(
      screen.getByText(
        "Echo will bring you back to this listening page after you sign in.",
      ),
    ).toBeVisible();
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute(
      "href",
      "/profile?next=%2Fbooks%2Fdocument-id%2Flisten",
    );
    expect(fetch).not.toHaveBeenCalled();
  });

  it("starts mock audio creation from a text-ready document", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(jsonResponse(textReadyAudio))
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
      .mockResolvedValueOnce(jsonResponse(readyAudio));

    render(<DocumentAudioPlayer documentId="document-id" />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Create listening audio" }),
    );

    expect(await screen.findByText("2 audio parts ready")).toBeVisible();
    expect(screen.getByText("Listening language: Cantonese")).toBeVisible();
    expect(screen.getByText("Page 1")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Part 1" })).toBeVisible();
    expect(fetchMock.mock.calls[1][0]).toContain("/prepare-audio");
  });

  it("shows the recording name with the saved upload as context", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        ...readyAudio,
        title: "Echo test",
        recording_title: "Chapter 1",
        original_filename: "chapter-1.pdf",
      }),
    );

    render(<DocumentAudioPlayer documentId="document-id" />);

    expect(
      await screen.findByRole("heading", { name: "Chapter 1" }),
    ).toBeVisible();
    expect(screen.getByText("from Echo test")).toBeVisible();
  });

  it("renames the current recording from the listening page", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(jsonResponse(readyAudio))
      .mockResolvedValueOnce(jsonResponse({ message: "renamed" }))
      .mockResolvedValueOnce(
        jsonResponse({
          ...readyAudio,
          recording_title: "Chapter 1",
        }),
    );

    render(<DocumentAudioPlayer documentId="document-id" />);

    fireEvent.click(await screen.findByRole("button", { name: "Rename recording" }));
    fireEvent.change(screen.getByLabelText("Recording name"), {
      target: { value: "Chapter 1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save name" }));

    expect(
      await screen.findByRole("heading", { name: "Chapter 1" }),
    ).toBeVisible();
    expect(fetchMock.mock.calls[1][0]).toContain("/api/books/document-id");
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: "PATCH" });
    expect(fetchMock.mock.calls[1][1]?.body).toBe(
      JSON.stringify({ title: "Chapter 1" }),
    );
  });

  it("links to the full recording audio download", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(readyAudio));

    render(<DocumentAudioPlayer documentId="document-id" />);

    expect(
      await screen.findByRole("link", { name: "Download recording" }),
    ).toHaveAttribute(
      "href",
      "http://localhost:8001/api/books/document-id/audio/download",
    );
  });

  it("links to uploading more pages for the saved upload", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(readyAudio));

    render(<DocumentAudioPlayer documentId="document-id" />);

    expect(await screen.findByRole("link", { name: "Upload more" })).toHaveAttribute(
      "href",
      "/books/new?folderId=folder-id&folderTitle=My+document",
    );
  });

  it("moves between ready audio segments", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(readyAudio));
    const { container } = render(<DocumentAudioPlayer documentId="document-id" />);

    expect(await screen.findByRole("heading", { name: "Part 1" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Next part" }));

    expect(screen.getByRole("heading", { name: "Part 2" })).toBeVisible();
    expect(container.querySelector("audio")?.getAttribute("src")).toContain(
      "/api/books/document-id/audio/2/file",
    );
  });

  it("offers to continue interrupted audio creation", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        ...textReadyAudio,
        processing_status: "generating_audio",
      }),
    );

    render(<DocumentAudioPlayer documentId="document-id" />);

    expect(
      await screen.findByRole("button", { name: "Continue creating audio" }),
    ).toBeVisible();
    expect(
      screen.getByText("Audio creation appears to have stopped. Continue to resume it."),
    ).toBeVisible();
  });

  it("offers to recover failed audio creation with existing segments", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          ...readyAudio,
          processing_status: "failed",
          segments: [
            {
              ...readyAudio.segments[0],
              audio_url: null,
              duration_seconds: null,
              processing_status: "failed",
              error_message: "Audio preparation stopped before it finished.",
            },
          ],
        }),
      )
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
      .mockResolvedValueOnce(jsonResponse(readyAudio));

    render(<DocumentAudioPlayer documentId="document-id" />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Continue creating audio" }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(screen.getByText("2 audio parts ready")).toBeVisible();
    expect(fetchMock.mock.calls[1][0]).toContain("/prepare-audio");
  });

  it("marks the document finished after the final segment ends", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(readyAudio));
    const { container } = render(<DocumentAudioPlayer documentId="document-id" />);

    expect(await screen.findByRole("heading", { name: "Part 1" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Next part" }));
    fireEvent.ended(container.querySelector("audio") as HTMLAudioElement);

    expect(screen.getByText("Finished this document.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Start over" })).toBeVisible();
    expect(
      JSON.parse(
        window.localStorage.getItem("echo:document-id:listening-progress") ?? "{}",
      ),
    ).toMatchObject({
      segmentNumber: 2,
      positionSeconds: 0,
      completed: true,
    });
  });
});
