"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useAuthSession } from "@/components/auth/use-auth-session";
import {
  deleteDocumentFolder,
  deleteDocumentRecording,
  folderAudioDownloadUrl,
  getDocumentLibrary,
  renameDocumentFolder,
  renameDocumentRecording,
  recordingAudioDownloadUrl,
} from "@/lib/api";
import { languageSummary } from "@/lib/listening-languages";
import type {
  DocumentLibraryFolder,
  DocumentLibraryItem,
  DocumentProcessingStatus,
} from "@/types/documents";


type SavedProgress = {
  segmentNumber?: number;
  playbackSpeed?: number;
  completed?: boolean;
};

const statusLabels: Record<DocumentProcessingStatus, string> = {
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

function progressKey(documentId: string): string {
  return `echo:${documentId}:listening-progress`;
}

function readSavedProgress(documentId: string): SavedProgress | null {
  const saved = window.localStorage.getItem(progressKey(documentId));
  if (!saved) return null;
  try {
    return JSON.parse(saved) as SavedProgress;
  } catch {
    window.localStorage.removeItem(progressKey(documentId));
    return null;
  }
}

function recordingHref(recording: DocumentLibraryItem): string {
  if (recording.processing_status === "ready") {
    return `/books/${recording.id}/listen`;
  }
  if (
    recording.processing_status === "text_ready" ||
    recording.processing_status === "generating_audio"
  ) {
    return `/books/${recording.id}/listen`;
  }
  return `/books/${recording.id}`;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function recordingLabel(recording: DocumentLibraryItem, index: number): string {
  return recording.recording_title ?? recording.original_filename ?? `Recording ${index + 1}`;
}

function uploadMoreHref(folder: DocumentLibraryFolder): string {
  const params = new URLSearchParams({
    folderId: folder.id,
    folderTitle: folder.title,
  });
  return `/books/new?${params.toString()}`;
}

function downloadableRecordings(folder: DocumentLibraryFolder): DocumentLibraryItem[] {
  return folder.recordings.filter(
    (recording) =>
      recording.processing_status === "ready" && recording.audio_segment_count > 0,
  );
}

export function DocumentLibrary() {
  const { session } = useAuthSession();
  const accessToken = session?.access_token ?? null;
  const openMenuRef = useRef<HTMLDivElement | null>(null);
  const selectedFolderIdRef = useRef<string | null>(null);
  const [folders, setFolders] = useState<DocumentLibraryFolder[]>([]);
  const [selectedFolderId, setSelectedFolderId] = useState<string | null>(null);
  const [progressByRecording, setProgressByRecording] = useState<
    Record<string, SavedProgress | null>
  >({});
  const [renameValue, setRenameValue] = useState("");
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [renamingRecordingId, setRenamingRecordingId] = useState<string | null>(null);
  const [recordingRenameValue, setRecordingRenameValue] = useState("");
  const [downloadChoicesOpen, setDownloadChoicesOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedFolder = useMemo(
    () => folders.find((folder) => folder.id === selectedFolderId) ?? null,
    [folders, selectedFolderId],
  );

  const refresh = useCallback(async () => {
    try {
      const library = await getDocumentLibrary();
      const nextSelectedFolder =
        library.folders.find((folder) => folder.id === selectedFolderIdRef.current) ??
        null;
      setFolders(library.folders);
      selectedFolderIdRef.current = nextSelectedFolder?.id ?? null;
      setSelectedFolderId(nextSelectedFolder?.id ?? null);
      setRenameValue(nextSelectedFolder?.title ?? "");
      setOpenMenu(null);
      setRenaming(false);
      setRenamingRecordingId(null);
      setRecordingRenameValue("");
      setDownloadChoicesOpen(false);
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
      await renameDocumentFolder(selectedFolder.id, renameValue);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Echo could not rename this upload.");
    } finally {
      setActing(false);
    }
  }

  async function renameRecording(recording: DocumentLibraryItem) {
    setActing(true);
    setError(null);
    try {
      await renameDocumentRecording(recording.id, recordingRenameValue);
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
      await deleteDocumentFolder(selectedFolder.id);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Echo could not remove this upload.");
    } finally {
      setActing(false);
    }
  }

  async function removeRecording(recording: DocumentLibraryItem) {
    if (!window.confirm(`Remove "${recording.title}" recording?`)) return;
    setActing(true);
    setError(null);
    try {
      await deleteDocumentRecording(recording.id);
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
        <div
          aria-hidden="true"
          className="mx-auto flex h-28 w-40 items-end justify-center gap-2"
        >
          <div className="h-20 w-12 rounded-t-lg border border-accent bg-[#edf4f7]" />
          <div className="h-24 w-12 rounded-t-lg border border-[#a9c5b3] bg-[#f4faf5]" />
          <div className="h-16 w-12 rounded-t-lg border border-[#d9b9b4] bg-[#fff3f1]" />
        </div>
        <h1 className="mt-6 text-3xl font-semibold">Start your Echo library</h1>
        <p className="mx-auto mt-3 max-w-md leading-7 text-muted">
          Upload a PDF or page photos. Echo will create your first saved upload and
          keep its recordings together here.
        </p>
        <Link
          href="/books/new"
          className="mt-6 inline-flex min-h-12 items-center justify-center rounded-xl bg-accent px-5 font-semibold text-white hover:bg-accent-dark"
        >
          Start uploading
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
                  setDownloadChoicesOpen(false);
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
                <span className="mt-1 block text-sm leading-6 text-muted">
                  {languageSummary(folder.target_languages)}
                </span>
                <span className="mt-3 block text-sm font-semibold text-accent">
                  {statusLabels[folder.processing_status]}
                </span>
              </button>
            );
          })}
        </div>
      </section>

      {selectedFolder ? (
        <section className="rounded-2xl border border-border bg-surface p-5 shadow-[0_14px_40px_rgba(48,55,61,0.05)] lg:sticky lg:top-6 lg:max-h-[calc(100vh-48px)] lg:overflow-y-auto">
          {downloadChoicesOpen && (
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="download-all-title"
              onMouseDown={() => setDownloadChoicesOpen(false)}
              className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(18,24,31,0.28)] p-4"
            >
              <div
                onMouseDown={(event) => event.stopPropagation()}
                className="w-full max-w-md rounded-2xl border border-border bg-white p-5 shadow-[0_24px_70px_rgba(48,55,61,0.22)]"
              >
                <h2 id="download-all-title" className="text-xl font-semibold">
                  How do you want to download this upload?
                </h2>
                <p className="mt-2 text-sm leading-6 text-muted">
                  Choose one format for all ready recordings in {selectedFolder.title}.
                </p>
                <div className="mt-5 grid gap-3">
                  <a
                    href={folderAudioDownloadUrl(selectedFolder.id, accessToken)}
                    download
                    onClick={() => setDownloadChoicesOpen(false)}
                    className="rounded-xl border border-accent bg-[#edf4f7] p-4 text-left hover:bg-[#e0eff4]"
                  >
                    <span className="block font-semibold text-accent">
                      Combine and download
                    </span>
                    <span className="mt-1 block text-sm leading-6 text-muted">
                      Creates one audio file, oldest recording first.
                    </span>
                  </a>
                  <button
                    type="button"
                    onClick={() => {
                      for (const recording of downloadableRecordings(selectedFolder)) {
                        window.open(
                          recordingAudioDownloadUrl(recording.id, accessToken),
                          "_blank",
                        );
                      }
                      setDownloadChoicesOpen(false);
                    }}
                    className="rounded-xl border border-border p-4 text-left hover:bg-[#f8f6f0]"
                  >
                    <span className="block font-semibold">Download individually</span>
                    <span className="mt-1 block text-sm leading-6 text-muted">
                      Keeps each ready recording as a separate download.
                    </span>
                  </button>
                </div>
                <button
                  type="button"
                  onClick={() => setDownloadChoicesOpen(false)}
                  className="mt-4 min-h-10 rounded-lg border border-border px-4 font-semibold hover:bg-[#f8f6f0]"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
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
              <p className="mt-1 text-sm text-muted">
                {languageSummary(selectedFolder.target_languages)}
              </p>
            </div>
            <div className="flex items-start gap-2">
              <button
                type="button"
                disabled={downloadableRecordings(selectedFolder).length === 0}
                onClick={() => {
                  setOpenMenu(null);
                  setDownloadChoicesOpen(true);
                }}
                className="inline-flex min-h-11 items-center justify-center rounded-lg border border-accent px-4 font-semibold text-accent hover:bg-[#edf4f7] disabled:cursor-not-allowed disabled:border-border disabled:text-muted disabled:hover:bg-transparent"
              >
                Download all
              </button>
              <Link
                href={uploadMoreHref(selectedFolder)}
                className="inline-flex min-h-11 items-center justify-center rounded-lg bg-accent px-4 font-semibold text-white hover:bg-accent-dark"
              >
                Upload more
              </Link>
              <div className="relative" ref={openMenu === "document" ? openMenuRef : null}>
              <button
                type="button"
                aria-haspopup="menu"
                aria-expanded={openMenu === "document"}
                aria-label="Document actions"
                onClick={() =>
                  setOpenMenu((open) => (open === "document" ? null : "document"))
                }
                className="flex size-11 items-center justify-center rounded-lg border border-border bg-white text-2xl font-semibold leading-none hover:bg-[#f8f6f0]"
              >
                ...
              </button>
              {openMenu === "document" && (
                <div
                  role="menu"
                  className="absolute right-0 z-50 mt-2 w-44 rounded-xl border border-border bg-white p-2 shadow-[0_14px_35px_rgba(48,55,61,0.12)]"
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
                    Rename saved upload
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
                    Remove saved upload
                  </button>
                </div>
              )}
              </div>
            </div>
          </div>

          {renaming && (
            <div className="mt-5 flex flex-col gap-3 rounded-xl border border-border bg-white p-4 sm:flex-row">
              <label className="flex-1">
                <span className="text-sm font-semibold text-muted">Saved upload name</span>
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
              const href = recordingHref(recording);
              const progress = progressByRecording[recording.id];
              const progressText = progress?.completed
                ? "Finished"
                : progress?.segmentNumber
                  ? `Saved at segment ${progress.segmentNumber}`
                  : "No saved listening position";

              return (
                <li
                  key={recording.id}
                  className="relative rounded-xl border border-border bg-white p-4 transition hover:border-accent hover:bg-[#fbfaf6]"
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
                        added {formatDate(recording.created_at)} ·{" "}
                        {progressText}
                      </p>
                    </div>
                    <Link
                      href={href}
                      aria-label={`Open ${recordingLabel(recording, index)}`}
                      className="absolute inset-0 rounded-xl focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2"
                    />
                    <div className="relative z-20 flex items-start">
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
                            className="absolute right-0 bottom-full z-50 mb-2 w-48 rounded-xl border border-border bg-white p-2 shadow-[0_14px_35px_rgba(48,55,61,0.12)]"
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
                    <div className="relative z-10 mt-4 flex flex-col gap-3 rounded-xl border border-border bg-[#f8f6f0] p-4 sm:flex-row">
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
      ) : (
        <section className="flex min-h-64 items-center justify-center rounded-2xl border border-dashed border-border bg-surface p-8 text-center shadow-[0_14px_40px_rgba(48,55,61,0.04)]">
          <div>
            <h2 className="text-2xl font-semibold">Select a folder to start</h2>
            <p className="mt-2 max-w-md leading-7 text-muted">
              Choose a saved upload from the library list to see its recordings and actions.
            </p>
          </div>
        </section>
      )}
    </div>
  );
}
