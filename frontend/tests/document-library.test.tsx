import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DocumentLibrary } from "@/components/documents/document-library";


const readyDocument = {
  id: "ready-book",
  library_book_id: "folder-id",
  title: "Ready upload",
  recording_title: null,
  target_language: "cantonese",
  tts_voice: "zh-HK-HiuMaanNeural",
  original_filename: "ready.pdf",
  source_type: "pdf",
  total_pages: 2,
  processing_status: "ready",
  error_message: null,
  completed_pages: 2,
  failed_pages: 0,
  audio_segment_count: 3,
  processing_active: false,
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-24T09:30:00Z",
};

const uploadedDocument = {
  ...readyDocument,
  id: "uploaded-book",
  library_book_id: "folder-id",
  title: "Uploaded upload",
  recording_title: null,
  original_filename: null,
  source_type: "images",
  total_pages: 1,
  processing_status: "uploaded",
  completed_pages: 0,
  audio_segment_count: 0,
};

const readyFolder = {
  id: "folder-id",
  title: "Ready upload",
  recording_count: 2,
  total_pages: 3,
  processing_status: "ready",
  processing_active: false,
  target_languages: ["cantonese"],
  latest_recording_at: "2026-07-24T09:30:00Z",
  recordings: [readyDocument, uploadedDocument],
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

async function selectReadyFolder() {
  fireEvent.click(await screen.findByRole("button", { name: /Ready upload/ }));
}

describe("document library", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    vi.spyOn(window, "confirm").mockReturnValue(true);
    installLocalStorageStub();
    window.localStorage.clear();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("shows document folders and recordings with saved listening progress", async () => {
    window.localStorage.setItem(
      "echo:ready-book:listening-progress",
      JSON.stringify({ segmentNumber: 2, positionSeconds: 12, playbackSpeed: 1.25 }),
    );
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({ folders: [readyFolder] }),
    );

    render(<DocumentLibrary />);

    expect(await screen.findByText("Select a folder to start")).toBeVisible();
    expect(screen.getByText(/Choose a saved upload/)).toBeVisible();
    expect(screen.queryByRole("link", { name: "Open ready.pdf" })).not.toBeInTheDocument();

    await selectReadyFolder();

    expect(screen.getAllByText("Ready upload")).toHaveLength(2);
    expect(screen.getByText(/2 recordings · 3 pages/)).toBeVisible();
    expect(screen.getAllByText("Cantonese")).toHaveLength(2);
    expect(screen.getByText("2 recordings")).toBeVisible();
    expect(screen.getByText("Recording 2")).toBeVisible();
    expect(screen.getAllByText(/added Jul 22/)).toHaveLength(2);
    expect(screen.getByText(/Saved at segment 2/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Open ready.pdf" })).toHaveAttribute(
      "href",
      "/books/ready-book/listen",
    );
    expect(screen.getByRole("link", { name: "Open Recording 2" })).toHaveAttribute(
      "href",
      "/books/uploaded-book",
    );
    expect(screen.getByRole("link", { name: "Upload more" })).toHaveAttribute(
      "href",
      "/books/new?folderId=folder-id&folderTitle=Ready+upload",
    );
    expect(screen.getByRole("button", { name: "Download all" })).toBeEnabled();
  });

  it("asks how to download all ready recordings in a folder", async () => {
    const openMock = vi.spyOn(window, "open").mockImplementation(() => null);
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({ folders: [readyFolder] }),
    );

    render(<DocumentLibrary />);

    await selectReadyFolder();
    fireEvent.click(screen.getByRole("button", { name: "Download all" }));

    expect(
      screen.getByRole("dialog", {
        name: "How do you want to download this upload?",
      }),
    ).toBeVisible();
    expect(
      screen.getByRole("link", {
        name: /Combine and downloadCreates one audio file/,
      }),
    ).toHaveAttribute(
      "href",
      "http://localhost:8001/api/books/folders/folder-id/audio/download",
    );
    expect(screen.getByText("Creates one audio file, oldest recording first.")).toBeVisible();
    expect(
      screen.getByText("Keeps each ready recording as a separate download."),
    ).toBeVisible();
    fireEvent.mouseDown(
      screen.getByRole("dialog", {
        name: "How do you want to download this upload?",
      }),
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Download all" }));

    fireEvent.click(
      screen.getByRole("button", {
        name: /Download individuallyKeeps each ready recording/,
      }),
    );

    expect(openMock).toHaveBeenCalledTimes(1);
    expect(openMock).toHaveBeenCalledWith(
      "http://localhost:8001/api/books/ready-book/audio/download",
      "_blank",
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("offers upload when the local library is empty", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ folders: [] }));

    render(<DocumentLibrary />);

    expect(await screen.findByText("Start your Echo library")).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Start uploading" }),
    ).toHaveAttribute("href", "/books/new");
  });

  it("renames a selected document folder", async () => {
    const renamedFolder = { ...readyFolder, title: "Renamed upload" };
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ folders: [readyFolder] }))
      .mockResolvedValueOnce(jsonResponse({ message: "renamed" }))
      .mockResolvedValueOnce(jsonResponse({ folders: [renamedFolder] }));

    render(<DocumentLibrary />);

    await selectReadyFolder();
    fireEvent.click(await screen.findByRole("button", { name: "Document actions" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Rename saved upload" }));
    const input = await screen.findByLabelText("Saved upload name");
    fireEvent.change(input, { target: { value: "Renamed upload" } });
    fireEvent.click(screen.getByRole("button", { name: "Save name" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(fetchMock.mock.calls[1][0]).toContain("/api/books/folders/folder-id");
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: "PATCH" });
  });

  it("closes the document actions menu from outside click and escape", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ folders: [readyFolder] }));

    render(<DocumentLibrary />);

    await selectReadyFolder();
    fireEvent.click(await screen.findByRole("button", { name: "Document actions" }));
    expect(screen.getByRole("menuitem", { name: "Rename saved upload" })).toBeVisible();
    fireEvent.mouseDown(screen.getByText("ready.pdf"));
    expect(
      screen.queryByRole("menuitem", { name: "Rename saved upload" }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Document actions" }));
    expect(screen.getByRole("menuitem", { name: "Rename saved upload" })).toBeVisible();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(
      screen.queryByRole("menuitem", { name: "Rename saved upload" }),
    ).not.toBeInTheDocument();
  });

  it("renames one recording from its actions menu", async () => {
    const renamedFolder = {
      ...readyFolder,
      recordings: [{ ...readyDocument, recording_title: "Opening section" }, uploadedDocument],
    };
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ folders: [readyFolder] }))
      .mockResolvedValueOnce(jsonResponse({ message: "renamed" }))
      .mockResolvedValueOnce(jsonResponse({ folders: [renamedFolder] }));

    render(<DocumentLibrary />);

    await selectReadyFolder();
    fireEvent.click(await screen.findByRole("button", { name: "ready.pdf actions" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Rename recording" }));
    const input = screen.getByLabelText("Recording name");
    fireEvent.change(input, { target: { value: "Opening section" } });
    fireEvent.click(screen.getByRole("button", { name: "Save name" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(fetchMock.mock.calls[1][0]).toContain("/api/books/ready-book");
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: "PATCH" });
  });

  it("keeps recording rename controls interactive inside a clickable card", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ folders: [readyFolder] }));

    render(<DocumentLibrary />);

    await selectReadyFolder();
    fireEvent.click(await screen.findByRole("button", { name: "ready.pdf actions" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Rename recording" }));
    const input = screen.getByLabelText("Recording name");
    fireEvent.click(input);
    fireEvent.change(input, { target: { value: "Renamed audio" } });

    expect(input).toHaveValue("Renamed audio");
    expect(screen.getByRole("button", { name: "Save name" })).toBeEnabled();
  });

  it("removes a selected document folder from the actions menu", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ folders: [readyFolder] }))
      .mockResolvedValueOnce(jsonResponse({ message: "removed" }))
      .mockResolvedValueOnce(jsonResponse({ folders: [] }));

    render(<DocumentLibrary />);

    await selectReadyFolder();
    fireEvent.click(await screen.findByRole("button", { name: "Document actions" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Remove saved upload" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(fetchMock.mock.calls[1][0]).toContain("/api/books/folders/folder-id");
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: "DELETE" });
  });

  it("removes one recording from a folder", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ folders: [readyFolder] }))
      .mockResolvedValueOnce(jsonResponse({ message: "removed" }))
      .mockResolvedValueOnce(jsonResponse({ folders: [] }));

    render(<DocumentLibrary />);

    await selectReadyFolder();
    fireEvent.click(await screen.findByRole("button", { name: "ready.pdf actions" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Remove recording" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(fetchMock.mock.calls[1][0]).toContain("/api/books/ready-book");
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: "DELETE" });
  });
});
