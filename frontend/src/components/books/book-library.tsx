"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  deleteBookFolder,
  deleteBookRecording,
  getBookLibrary,
  renameBookFolder,
  renameBookRecording,
} from "@/lib/api";
import type {
  BookLibraryFolder,
  BookLibraryItem,
  BookProcessingStatus,
} from "@/types/books";


type SavedProgress = {
  segmentNumber?: number;
  playbackSpeed?: number;
  completed?: boolean;
};

const statusLabels: Record<BookProcessingStatus, string> = {
  uploaded: "Text not started",
  normalizing_pages: "Preparing pages",
  inspecting: "Checking pages",
  extracting_text: "Reading text",
  running_ocr: "Reading text",
  text_ready: "Ready for audio",
  generating_audio: "Creating audio",
  ready: "Ready to listen",
  failed: "Needs attention",
};

function progressKey(bookId: string): string {
  return `echo:${bookId}:listening-progress`;
}

function readSavedProgress(bookId: string): SavedProgress | null {
  const saved = window.localStorage.getItem(progressKey(bookId));
  if (!saved) return null;
  try {
    return JSON.parse(saved) as SavedProgress;
  } catch {
    window.localStorage.removeItem(progressKey(bookId));
    return null;
  }
}

function actionFor(recording: BookLibraryItem): { href: string; label: string } {
  if (recording.processing_status === "ready") {
    return { href: `/books/${recording.id}/listen`, label: "Listen" };
  }
  if (
    recording.processing_status === "text_ready" ||
    recording.processing_status === "generating_audio"
  ) {
    return { href: `/books/${recording.id}/listen`, label: "Create audio" };
  }
  return { href: `/books/${recording.id}`, label: "Prepare text" };
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function recordingLabel(recording: BookLibraryItem, index: number): string {
  return recording.recording_title ?? recording.original_filename ?? `Recording ${index + 1}`;
}

export function BookLibrary() {
  const openMenuRef = useRef<HTMLDivElement | null>(null);
  const selectedFolderIdRef = useRef<string | null>(null);
  const [folders, setFolders] = useState<BookLibraryFolder[]>([]);
  const [selectedFolderId, setSelectedFolderId] = useState<string | null>(null);
  const [progressByRecording, setProgressByRecording] = useState<
    Record<string, SavedProgress | null>
  >({});
  const [renameValue, setRenameValue] = useState("");
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [renamingRecordingId, setRenamingRecordingId] = useState<string | null>(null);
  const [recordingRenameValue, setRecordingRenameValue] = useState("");
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedFolder = useMemo(
    () => folders.find((folder) => folder.id === selectedFolderId) ?? null,
    [folders, selectedFolderId],
  );

  const refresh = useCallback(async () => {
    try {
      const library = await getBookLibrary();
      const nextSelectedFolder =
        library.folders.find((folder) => folder.id === selectedFolderIdRef.current) ??
        library.folders[0] ??
        null;
      setFolders(library.folders);
      selectedFolderIdRef.current = nextSelectedFolder?.id ?? null;
      setSelectedFolderId(nextSelectedFolder?.id ?? null);
      setRenameValue(nextSelectedFolder?.title ?? "");
      setOpenMenu(null);
      setRenaming(false);
      setRenamingRecordingId(null);
      setRecordingRenameValue("");
      setProgressByRecording(
        Object.fromEntries(
          library.folders.flatMap((folder) =>
            folder.recordings.map((recording) => [
              recording.id,
              readSavedProgress(recording.id),
            ]),
          ),
        ),
      );
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Echo could not load your local library.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  useEffect(() => {
    function closeMenus(event: MouseEvent) {
      if (
        openMenuRef.current &&
        event.target instanceof Node &&
        !openMenuRef.current.contains(event.target)
      ) {
        setOpenMenu(null);
      }
    }

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpenMenu(null);
    }

    document.addEventListener("mousedown", closeMenus);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeMenus);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, []);

  async function renameSelectedFolder() {
    if (!selectedFolder) return;
    setActing(true);
    setError(null);
    try {
      await renameBookFolder(selectedFolder.id, renameValue);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Echo could not rename this book.");
    } finally {
      setActing(false);
    }
  }

  async function renameRecording(recording: BookLibraryItem) {
    setActing(true);
    setError(null);
    try {
      await renameBookRecording(recording.id, recordingRenameValue);
      await refresh();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Echo could not rename this recording.",
      );
    } finally {
      setActing(false);
    }
  }

  async function removeSelectedFolder() {
    if (!selectedFolder) return;
    if (!window.confirm(`Remove "${selectedFolder.title}" and all recordings?`)) return;
    setActing(true);
    setError(null);
    try {
      await deleteBookFolder(selectedFolder.id);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Echo could not remove this book.");
    } finally {
      setActing(false);
    }
  }

  async function removeRecording(recording: BookLibraryItem) {
    if (!window.confirm(`Remove "${recording.title}" recording?`)) return;
    setActing(true);
    setError(null);
    try {
      await deleteBookRecording(recording.id);
      window.localStorage.removeItem(progressKey(recording.id));
      await refresh();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Echo could not remove this recording.",
      );
    } finally {
      setActing(false);
    }
  }

  if (loading) {
    return <p className="mt-10 text-lg text-muted">Loading your library...</p>;
  }

  if (error && folders.length === 0) {
    return (
      <div className="mt-8 rounded-2xl border border-[#d9b9b4] bg-[#fff3f1] p-5">
        <p role="alert" className="text-[#783a33]">
          {error}
        </p>
        <button
          type="button"
          onClick={() => void refresh()}
          className="mt-4 min-h-11 rounded-lg border border-[#d9b9b4] px-4 font-semibold text-[#783a33]"
        >
          Try again
        </button>
      </div>
    );
  }

  if (folders.length === 0) {
    return (
      <section className="mx-auto mt-16 max-w-xl rounded-3xl border border-border bg-surface p-8 text-center shadow-[0_20px_60px_rgba(48,55,61,0.06)]">
        <h1 className="text-3xl font-semibold">Your library is empty</h1>
        <p className="mx-auto mt-3 max-w-md leading-7 text-muted">
          Upload a PDF or page photos to create your first local Echo book.
        </p>
        <Link
          href="/books/new"
          className="mt-6 inline-flex min-h-12 items-center justify-center rounded-xl bg-accent px-5 font-semibold text-white hover:bg-accent-dark"
        >
          Upload your book
        </Link>
      </section>
    );
  }

  return (
    <div className="mt-8 grid gap-7 lg:grid-cols-[320px_minmax(0,1fr)] lg:items-start">
      <section className="rounded-2xl border border-border bg-surface p-3 shadow-[0_14px_40px_rgba(48,55,61,0.05)] lg:max-h-[calc(100vh-220px)] lg:overflow-y-auto">
        <div className="space-y-2">
          {folders.map((folder) => {
            const isSelected = folder.id === selectedFolderId;
            return (
              <button
                key={folder.id}
                type="button"
                onClick={() => {
                  selectedFolderIdRef.current = folder.id;
                  setSelectedFolderId(folder.id);
                  setRenameValue(folder.title);
                  setOpenMenu(null);
                  setRenaming(false);
                  setRenamingRecordingId(null);
                  setRecordingRenameValue("");
                }}
                className={`w-full rounded-xl border p-4 text-left transition ${
                  isSelected
                    ? "border-accent bg-[#edf4f7]"
                    : "border-border bg-surface hover:border-accent"
                }`}
              >
                <span className="block text-lg font-semibold leading-tight">
                  {folder.title}
                </span>
                <span className="mt-2 block text-sm leading-6 text-muted">
                  {folder.recording_count} recording
                  {folder.recording_count === 1 ? "" : "s"}
                  {" · "}
                  {folder.total_pages} page
                  {folder.total_pages === 1 ? "" : "s"}
                </span>
                <span className="mt-3 block text-sm font-semibold text-accent">
                  {statusLabels[folder.processing_status]}
                </span>
              </button>
            );
          })}
        </div>
      </section>

      {selectedFolder && (
        <section className="rounded-2xl border border-border bg-surface p-5 shadow-[0_14px_40px_rgba(48,55,61,0.05)] lg:sticky lg:top-6 lg:max-h-[calc(100vh-48px)] lg:overflow-y-auto">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-sm font-bold text-accent">
                {selectedFolder.recording_count} recording
                {selectedFolder.recording_count === 1 ? "" : "s"}
              </p>
              <h2 className="mt-1 text-3xl font-semibold">{selectedFolder.title}</h2>
              <p className="mt-2 text-sm text-muted">
                {selectedFolder.total_pages} total page
                {selectedFolder.total_pages === 1 ? "" : "s"} · updated{" "}
                {formatDate(selectedFolder.latest_recording_at)}
              </p>
            </div>
            <div className="relative" ref={openMenu === "book" ? openMenuRef : null}>
              <button
                type="button"
                aria-haspopup="menu"
                aria-expanded={openMenu === "book"}
                aria-label="Book actions"
                onClick={() => setOpenMenu((open) => (open === "book" ? null : "book"))}
                className="flex size-11 items-center justify-center rounded-lg border border-border bg-white text-2xl font-semibold leading-none hover:bg-[#f8f6f0]"
              >
                ...
              </button>
              {openMenu === "book" && (
                <div
                  role="menu"
                  className="absolute right-0 z-10 mt-2 w-44 rounded-xl border border-border bg-white p-2 shadow-[0_14px_35px_rgba(48,55,61,0.12)]"
                >
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setRenaming(true);
                      setOpenMenu(null);
                    }}
                    className="min-h-10 w-full rounded-lg px-3 text-left font-semibold hover:bg-[#f8f6f0]"
                  >
                    Rename book
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    disabled={acting}
                    onClick={() => {
                      setOpenMenu(null);
                      void removeSelectedFolder();
                    }}
                    className="min-h-10 w-full rounded-lg px-3 text-left font-semibold text-[#783a33] hover:bg-[#fff3f1] disabled:opacity-60"
                  >
                    Remove book
                  </button>
                </div>
              )}
            </div>
          </div>

          {renaming && (
            <div className="mt-5 flex flex-col gap-3 rounded-xl border border-border bg-white p-4 sm:flex-row">
              <label className="flex-1">
                <span className="text-sm font-semibold text-muted">Book name</span>
                <input
                  value={renameValue}
                  onChange={(event) => setRenameValue(event.target.value)}
                  className="mt-2 min-h-11 w-full rounded-lg border border-border bg-white px-3"
                />
              </label>
              <div className="flex gap-2 self-end">
                <button
                  type="button"
                  onClick={() => {
                    setRenameValue(selectedFolder.title);
                    setRenaming(false);
                  }}
                  className="min-h-11 rounded-lg border border-border px-4 font-semibold hover:bg-[#f8f6f0]"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={acting || renameValue.trim() === selectedFolder.title}
                  onClick={() => void renameSelectedFolder()}
                  className="min-h-11 rounded-lg bg-accent px-4 font-semibold text-white hover:bg-accent-dark disabled:opacity-60"
                >
                  Save name
                </button>
              </div>
            </div>
          )}

          {error && (
            <p
              role="alert"
              className="mt-4 rounded-xl border border-[#d9b9b4] bg-[#fff3f1] p-3 text-sm text-[#783a33]"
            >
              {error}
            </p>
          )}

          <ol className="mt-6 space-y-3">
            {selectedFolder.recordings.map((recording, index) => {
              const action = actionFor(recording);
              const progress = progressByRecording[recording.id];
              const progressText = progress?.completed
                ? "Finished"
                : progress?.segmentNumber
                  ? `Saved at segment ${progress.segmentNumber}`
                  : "No saved listening position";

              return (
                <li
                  key={recording.id}
                  className="rounded-xl border border-border bg-white p-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <p className="text-sm font-bold text-accent">
                        {statusLabels[recording.processing_status]}
                      </p>
                      <h3 className="mt-1 text-lg font-semibold">
                        {recordingLabel(recording, index)}
                      </h3>
                      <p className="mt-1 text-sm text-muted">
                        {recording.total_pages} page
                        {recording.total_pages === 1 ? "" : "s"} ·{" "}
                        {recording.audio_segment_count} audio segment
                        {recording.audio_segment_count === 1 ? "" : "s"} ·{" "}
                        {progressText}
                      </p>
                    </div>
                    <div className="flex w-full items-start gap-2 sm:w-auto">
                      <Link
                        href={action.href}
                        className="inline-flex min-h-10 min-w-28 items-center justify-center rounded-lg bg-accent px-3 font-semibold text-white hover:bg-accent-dark"
                      >
                        {action.label}
                      </Link>
                      <div
                        className="relative"
                        ref={
                          openMenu === `recording:${recording.id}`
                            ? openMenuRef
                            : null
                        }
                      >
                        <button
                          type="button"
                          aria-haspopup="menu"
                          aria-expanded={openMenu === `recording:${recording.id}`}
                          aria-label={`${recordingLabel(recording, index)} actions`}
                          onClick={() =>
                            setOpenMenu((open) =>
                              open === `recording:${recording.id}`
                                ? null
                                : `recording:${recording.id}`,
                            )
                          }
                          className="flex size-10 items-center justify-center rounded-lg border border-border bg-white text-xl font-semibold leading-none hover:bg-[#f8f6f0]"
                        >
                          ...
                        </button>
                        {openMenu === `recording:${recording.id}` && (
                          <div
                            role="menu"
                            className="absolute right-0 z-10 mt-2 w-48 rounded-xl border border-border bg-white p-2 shadow-[0_14px_35px_rgba(48,55,61,0.12)]"
                          >
                            <button
                              type="button"
                              role="menuitem"
                              onClick={() => {
                                setRenamingRecordingId(recording.id);
                                setRecordingRenameValue(recordingLabel(recording, index));
                                setOpenMenu(null);
                              }}
                              className="min-h-10 w-full rounded-lg px-3 text-left font-semibold hover:bg-[#f8f6f0]"
                            >
                              Rename recording
                            </button>
                            <button
                              type="button"
                              role="menuitem"
                              disabled={acting}
                              onClick={() => {
                                setOpenMenu(null);
                                void removeRecording(recording);
                              }}
                              className="min-h-10 w-full rounded-lg px-3 text-left font-semibold text-[#783a33] hover:bg-[#fff3f1] disabled:opacity-60"
                            >
                              Remove recording
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                  {renamingRecordingId === recording.id && (
                    <div className="mt-4 flex flex-col gap-3 rounded-xl border border-border bg-[#f8f6f0] p-4 sm:flex-row">
                      <label className="flex-1">
                        <span className="text-sm font-semibold text-muted">
                          Recording name
                        </span>
                        <input
                          value={recordingRenameValue}
                          onChange={(event) =>
                            setRecordingRenameValue(event.target.value)
                          }
                          className="mt-2 min-h-11 w-full rounded-lg border border-border bg-white px-3"
                        />
                      </label>
                      <div className="flex gap-2 self-end">
                        <button
                          type="button"
                          onClick={() => {
                            setRenamingRecordingId(null);
                            setRecordingRenameValue("");
                          }}
                          className="min-h-11 rounded-lg border border-border px-4 font-semibold hover:bg-white"
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          disabled={
                            acting ||
                            recordingRenameValue.trim() ===
                              recordingLabel(recording, index)
                          }
                          onClick={() => void renameRecording(recording)}
                          className="min-h-11 rounded-lg bg-accent px-4 font-semibold text-white hover:bg-accent-dark disabled:opacity-60"
                        >
                          Save name
                        </button>
                      </div>
                    </div>
                  )}
                </li>
              );
            })}
          </ol>
        </section>
      )}
    </div>
  );
}
