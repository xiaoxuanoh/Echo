"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  audioFileUrl,
  getDocumentAudio,
  prepareDocumentAudio,
  recordingAudioDownloadUrl,
  renameDocumentRecording,
} from "@/lib/api";
import { useAuthSession } from "@/components/auth/use-auth-session";
import { profileHrefForNext } from "@/lib/auth-redirect";
import type { AudioSegment, DocumentAudio, DocumentProcessingStatus } from "@/types/documents";


const activeStatuses = new Set<DocumentProcessingStatus>(["generating_audio"]);

const speedOptions = [0.75, 1, 1.25, 1.5, 2] as const;

type SavedProgress = {
  segmentNumber: number;
  positionSeconds: number;
  playbackSpeed: number;
  completed?: boolean;
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

function completedSegments(segments: AudioSegment[]): AudioSegment[] {
  return segments
    .filter(
      (segment) =>
        segment.processing_status === "completed" && segment.audio_url !== null,
    )
    .sort((left, right) => left.segment_number - right.segment_number);
}

function listeningTitle(documentAudio: DocumentAudio): string {
  return documentAudio.recording_title ?? documentAudio.original_filename ?? documentAudio.title;
}

function uploadMoreHref(documentAudio: DocumentAudio): string {
  const params = new URLSearchParams({
    folderId: documentAudio.library_book_id,
    folderTitle: documentAudio.title,
  });
  return `/books/new?${params.toString()}`;
}

export function DocumentAudioPlayer({ documentId }: { documentId: string }) {
  const { isConfigured, isLoadingSession, session } = useAuthSession();
  const accessToken = session?.access_token ?? null;
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const progressRestoredRef = useRef(false);
  const [documentAudio, setDocumentAudio] = useState<DocumentAudio | null>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [completed, setCompleted] = useState(false);
  const [pendingSeek, setPendingSeek] = useState<number | null>(null);
  const [renamingRecording, setRenamingRecording] = useState(false);
  const [recordingName, setRecordingName] = useState("");
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requiresSignIn = isConfigured && !isLoadingSession && !session;
  const canFetchDocument = !isConfigured || Boolean(session);

  const segments = useMemo(
    () => completedSegments(documentAudio?.segments ?? []),
    [documentAudio],
  );
  const currentSegment = segments[currentIndex] ?? null;

  const refresh = useCallback(async () => {
    if (!canFetchDocument) return;
    try {
      const nextDocumentAudio = await getDocumentAudio(documentId);
      setDocumentAudio(nextDocumentAudio);
      setRecordingName(listeningTitle(nextDocumentAudio));
      if (!progressRestoredRef.current) {
        const progress = readSavedProgress(documentId);
        const readySegments = completedSegments(nextDocumentAudio.segments);
        if (progress) {
          if (Number.isFinite(progress.playbackSpeed)) {
            setPlaybackSpeed(progress.playbackSpeed);
          }
          setCompleted(progress.completed === true);
          if (Number.isFinite(progress.positionSeconds)) {
            setPendingSeek(progress.positionSeconds);
          }
          const segmentIndex = readySegments.findIndex(
            (segment) => segment.segment_number === progress.segmentNumber,
          );
          if (segmentIndex >= 0) setCurrentIndex(segmentIndex);
        }
        progressRestoredRef.current = true;
      }
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Echo could not load the listening page.",
      );
    } finally {
      setLoading(false);
    }
  }, [canFetchDocument, documentId]);

  useEffect(() => {
    if (isLoadingSession || !canFetchDocument) return;
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer);
  }, [canFetchDocument, isLoadingSession, refresh]);

  useEffect(() => {
    if (
      !documentAudio ||
      !activeStatuses.has(documentAudio.processing_status) ||
      !documentAudio.processing_active
    ) {
      return;
    }
    const timer = window.setInterval(() => void refresh(), 1500);
    return () => window.clearInterval(timer);
  }, [documentAudio, refresh]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.playbackRate = playbackSpeed;
  }, [playbackSpeed, currentSegment]);

  function saveProgress(positionSeconds?: number, isCompleted = completed) {
    if (!currentSegment) return;
    window.localStorage.setItem(
      progressKey(documentId),
      JSON.stringify({
        segmentNumber: currentSegment.segment_number,
        positionSeconds: positionSeconds ?? audioRef.current?.currentTime ?? 0,
        playbackSpeed,
        completed: isCompleted,
      }),
    );
  }

  async function startAudio() {
    setActing(true);
    setError(null);
    try {
      await prepareDocumentAudio(documentId);
      await refresh();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Echo could not start creating listening audio.",
      );
    } finally {
      setActing(false);
    }
  }

  async function renameRecording() {
    if (!documentAudio) return;
    setActing(true);
    setError(null);
    try {
      await renameDocumentRecording(documentAudio.book_id, recordingName);
      await refresh();
      setRenamingRecording(false);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Echo could not rename this recording.",
      );
    } finally {
      setActing(false);
    }
  }

  function moveTo(nextIndex: number) {
    if (nextIndex < 0 || nextIndex >= segments.length) return;
    setCompleted(false);
    setCurrentIndex(nextIndex);
    setPendingSeek(0);
  }

  function startOver() {
    if (segments.length === 0) return;
    setCompleted(false);
    setCurrentIndex(0);
    setPendingSeek(0);
  }

  if (isLoadingSession) {
    return <p className="mt-10 text-lg text-muted">Loading the listening page…</p>;
  }

  if (requiresSignIn) {
    return (
      <div className="mt-10 rounded-2xl border border-border bg-surface p-5">
        <h1 className="text-2xl font-semibold">Sign in to listen</h1>
        <p className="mt-2 text-muted">
          Echo will bring you back to this listening page after you sign in.
        </p>
        <Link
          href={profileHrefForNext(`/books/${documentId}/listen`)}
          className="mt-4 inline-flex min-h-11 items-center rounded-lg bg-accent px-4 font-semibold text-white hover:bg-accent-dark"
        >
          Sign in
        </Link>
      </div>
    );
  }

  if (loading) {
    return <p className="mt-10 text-lg text-muted">Loading the listening page…</p>;
  }

  if (!documentAudio) {
    return (
      <div className="mt-10 rounded-2xl border border-[#d9b9b4] bg-[#fff3f1] p-5">
        <p role="alert" className="text-[#783a33]">
          {error || "Echo could not load the listening page."}
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

  const canResumeAudio =
    (documentAudio.processing_status === "generating_audio" &&
      !documentAudio.processing_active) ||
    (documentAudio.processing_status === "failed" && documentAudio.segments.length > 0);
  const canStart =
    documentAudio.processing_status === "text_ready" ||
    canResumeAudio;
  const title = listeningTitle(documentAudio);
  const showUploadContext = title !== documentAudio.title;

  return (
    <div className="mt-3">
      <section className="rounded-2xl border border-border bg-surface p-5 shadow-[0_14px_40px_rgba(48,55,61,0.05)] sm:p-6">
        <p className="text-sm font-bold tracking-[0.12em] text-accent uppercase">
          Listening to
        </p>
        <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold sm:text-4xl">
              {title}
            </h1>
            {showUploadContext && (
              <p className="mt-1 text-muted">from {documentAudio.title}</p>
            )}
            <p className="mt-1 text-muted">
              {segments.length > 0
                ? `${segments.length} audio part${segments.length === 1 ? "" : "s"} ready`
                : "No listening audio yet"}
            </p>
          </div>
          <div className="flex flex-col items-stretch gap-3 sm:min-w-60 sm:items-stretch">
            {canStart && (
              <button
                type="button"
                disabled={acting}
                onClick={() => void startAudio()}
                className="min-h-12 rounded-xl bg-accent px-6 py-3 font-semibold text-white shadow-sm hover:bg-accent-dark disabled:opacity-60"
              >
                {acting
                  ? "Starting…"
                  : documentAudio.processing_status === "text_ready"
                    ? "Create listening audio"
                    : "Continue creating audio"}
              </button>
            )}
            <Link
              href={uploadMoreHref(documentAudio)}
              className="inline-flex min-h-12 items-center justify-center rounded-xl bg-accent px-6 py-3 font-semibold text-white shadow-sm hover:bg-accent-dark"
            >
              Upload more
            </Link>
            <div className="flex flex-col gap-2 sm:flex-row">
              <button
                type="button"
                aria-label="Rename recording"
                onClick={() => {
                  setRecordingName(title);
                  setRenamingRecording(true);
                }}
                className="min-h-11 flex-1 rounded-lg border border-border bg-white px-4 font-semibold hover:bg-[#f8f6f0]"
              >
                Rename
              </button>
              {segments.length > 0 && (
                <a
                  href={recordingAudioDownloadUrl(documentAudio.book_id, accessToken)}
                  download
                  aria-label="Download recording"
                  className="inline-flex min-h-11 flex-1 items-center justify-center rounded-lg border border-border bg-white px-4 font-semibold hover:bg-[#f8f6f0]"
                >
                  Download
                </a>
              )}
            </div>
          </div>
        </div>

        {renamingRecording && (
          <div className="mt-5 flex flex-col gap-3 rounded-xl border border-border bg-white p-4 sm:flex-row">
            <label className="flex-1">
              <span className="text-sm font-semibold text-muted">Recording name</span>
              <input
                value={recordingName}
                onChange={(event) => setRecordingName(event.target.value)}
                className="mt-2 min-h-11 w-full rounded-lg border border-border bg-white px-3"
              />
            </label>
            <div className="flex gap-2 self-end">
              <button
                type="button"
                onClick={() => {
                  setRecordingName(title);
                  setRenamingRecording(false);
                }}
                className="min-h-11 rounded-lg border border-border px-4 font-semibold hover:bg-[#f8f6f0]"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={acting || recordingName.trim() === title}
                onClick={() => void renameRecording()}
                className="min-h-11 rounded-lg bg-accent px-4 font-semibold text-white hover:bg-accent-dark disabled:opacity-60"
              >
                Save name
              </button>
            </div>
          </div>
        )}

        {documentAudio.processing_status === "generating_audio" &&
          documentAudio.processing_active && (
            <p className="mt-4 rounded-xl border border-[#d2c69e] bg-[#fff9e8] p-4 text-[#6d5a22]">
              Echo is creating local mock audio. This page will update shortly.
            </p>
          )}
        {documentAudio.processing_status === "generating_audio" &&
          !documentAudio.processing_active && (
            <p className="mt-4 rounded-xl border border-[#d2c69e] bg-[#fff9e8] p-4 text-[#6d5a22]">
              Audio creation appears to have stopped. Continue to resume it.
            </p>
          )}
        {documentAudio.processing_status === "failed" && documentAudio.segments.length > 0 && (
          <p className="mt-4 rounded-xl border border-[#d2c69e] bg-[#fff9e8] p-4 text-[#6d5a22]">
            Audio creation stopped before it finished. Continue to recover local audio
            or resume the unfinished parts.
          </p>
        )}
        {documentAudio.processing_status !== "text_ready" &&
          documentAudio.processing_status !== "generating_audio" &&
          documentAudio.processing_status !== "failed" &&
          documentAudio.processing_status !== "ready" && (
            <p className="mt-4 rounded-xl border border-[#d2c69e] bg-[#fff9e8] p-4 text-[#6d5a22]">
              Prepare the page text before creating listening audio.
            </p>
          )}
        {error && (
          <p
            role="alert"
            className="mt-4 rounded-xl border border-[#d9b9b4] bg-[#fff3f1] p-4 text-[#783a33]"
          >
            {error}
          </p>
        )}
      </section>

      {segments.length > 1 && (
        <section className="mt-5 rounded-2xl border border-border bg-surface p-5 sm:p-6">
          <h2 className="text-2xl font-semibold">Audio parts</h2>
          <div className="mt-4 max-h-56 overflow-y-auto pr-2">
            <ol className="space-y-2">
              {segments.map((segment, index) => (
                <li key={segment.id}>
                  <button
                    type="button"
                    onClick={() => moveTo(index)}
                    className={`min-h-11 w-full rounded-lg border px-4 text-left font-semibold ${
                      index === currentIndex
                        ? "border-accent bg-[#edf4f7] text-accent"
                        : "border-border bg-white hover:bg-[#f8f6f0]"
                    }`}
                  >
                    Part {segment.segment_number}
                    {segment.page_number ? ` · page ${segment.page_number}` : ""}
                  </button>
                </li>
              ))}
            </ol>
          </div>
        </section>
      )}

      {currentSegment && (
        <section className="mt-5 rounded-2xl border border-border bg-surface p-5 sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-sm font-semibold text-muted">
                {currentSegment.page_number
                  ? `Page ${currentSegment.page_number}`
                  : "Prepared text"}
              </p>
              <h2 className="mt-1 text-2xl font-semibold">
                Part {currentSegment.segment_number}
              </h2>
            </div>
            <label className="flex items-center gap-3 text-sm font-semibold text-muted">
              Speed
              <select
                value={playbackSpeed}
                onChange={(event) => {
                  const nextSpeed = Number(event.target.value);
                  setPlaybackSpeed(nextSpeed);
                  saveProgress();
                }}
                className="min-h-11 rounded-lg border border-border bg-white px-3 text-foreground"
              >
                {speedOptions.map((speed) => (
                  <option key={speed} value={speed}>
                    {speed}×
                  </option>
                ))}
              </select>
            </label>
          </div>

          <audio
            key={currentSegment.id}
            ref={audioRef}
            controls
            src={audioFileUrl(currentSegment.audio_url ?? "", accessToken)}
            className="mt-6 w-full"
            onLoadedMetadata={() => {
              const audio = audioRef.current;
              if (!audio) return;
              audio.playbackRate = playbackSpeed;
              if (pendingSeek !== null) {
                audio.currentTime = pendingSeek;
                setPendingSeek(null);
              }
            }}
            onTimeUpdate={() => saveProgress()}
            onEnded={() => {
              if (currentIndex >= segments.length - 1) {
                setCompleted(true);
                saveProgress(0, true);
                return;
              }
              saveProgress(0, false);
              moveTo(currentIndex + 1);
            }}
          />

          <div className="mt-5 flex flex-wrap gap-3">
            <button
              type="button"
              disabled={currentIndex === 0}
              onClick={() => moveTo(currentIndex - 1)}
              className="min-h-11 rounded-lg border border-border px-4 font-semibold hover:bg-[#f8f6f0] disabled:opacity-50"
            >
              Previous part
            </button>
            <button
              type="button"
              disabled={currentIndex >= segments.length - 1}
              onClick={() => moveTo(currentIndex + 1)}
              className="min-h-11 rounded-lg border border-border px-4 font-semibold hover:bg-[#f8f6f0] disabled:opacity-50"
            >
              Next part
            </button>
            {completed && (
              <button
                type="button"
                onClick={startOver}
                className="min-h-11 rounded-lg bg-accent px-4 font-semibold text-white hover:bg-accent-dark"
              >
                Start over
              </button>
            )}
          </div>

          {completed && (
            <p className="mt-4 rounded-xl border border-[#a9c5b3] bg-[#f4faf5] p-4 text-[#376247]">
              Finished this document.
            </p>
          )}

          <details className="mt-6 rounded-xl bg-[#f8f6f0] p-4">
            <summary className="cursor-pointer font-semibold">
              Review source text
            </summary>
            <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-muted">
              {currentSegment.source_text}
            </p>
          </details>
        </section>
      )}

    </div>
  );
}
