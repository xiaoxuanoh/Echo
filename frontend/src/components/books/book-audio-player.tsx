"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { audioFileUrl, getBookAudio, prepareBookAudio } from "@/lib/api";
import type { AudioSegment, BookAudio, BookProcessingStatus } from "@/types/books";


const activeStatuses = new Set<BookProcessingStatus>(["generating_audio"]);

const speedOptions = [0.75, 1, 1.25, 1.5, 2] as const;

type SavedProgress = {
  segmentNumber: number;
  positionSeconds: number;
  playbackSpeed: number;
  completed?: boolean;
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

function completedSegments(segments: AudioSegment[]): AudioSegment[] {
  return segments
    .filter(
      (segment) =>
        segment.processing_status === "completed" && segment.audio_url !== null,
    )
    .sort((left, right) => left.segment_number - right.segment_number);
}

export function BookAudioPlayer({ bookId }: { bookId: string }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const progressRestoredRef = useRef(false);
  const [bookAudio, setBookAudio] = useState<BookAudio | null>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [completed, setCompleted] = useState(false);
  const [pendingSeek, setPendingSeek] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const segments = useMemo(
    () => completedSegments(bookAudio?.segments ?? []),
    [bookAudio],
  );
  const currentSegment = segments[currentIndex] ?? null;

  const refresh = useCallback(async () => {
    try {
      const nextAudio = await getBookAudio(bookId);
      setBookAudio(nextAudio);
      if (!progressRestoredRef.current) {
        const progress = readSavedProgress(bookId);
        const readySegments = completedSegments(nextAudio.segments);
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
  }, [bookId]);

  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  useEffect(() => {
    if (
      !bookAudio ||
      !activeStatuses.has(bookAudio.processing_status) ||
      !bookAudio.processing_active
    ) {
      return;
    }
    const timer = window.setInterval(() => void refresh(), 1500);
    return () => window.clearInterval(timer);
  }, [bookAudio, refresh]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.playbackRate = playbackSpeed;
  }, [playbackSpeed, currentSegment]);

  function saveProgress(positionSeconds?: number, isCompleted = completed) {
    if (!currentSegment) return;
    window.localStorage.setItem(
      progressKey(bookId),
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
      await prepareBookAudio(bookId);
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

  if (loading) {
    return <p className="mt-10 text-lg text-muted">Loading the listening page…</p>;
  }

  if (!bookAudio) {
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

  const canStart =
    bookAudio.processing_status === "text_ready" ||
    (bookAudio.processing_status === "generating_audio" &&
      !bookAudio.processing_active);

  return (
    <div className="mt-8">
      <section className="rounded-3xl border border-border bg-surface p-6 shadow-[0_20px_60px_rgba(48,55,61,0.06)] sm:p-8">
        <p className="text-sm font-bold tracking-[0.14em] text-accent uppercase">
          Listen
        </p>
        <div className="mt-2 flex flex-wrap items-start justify-between gap-5">
          <div>
            <h1 className="text-3xl font-semibold tracking-[-0.02em] sm:text-4xl">
              {bookAudio.title}
            </h1>
            <p className="mt-2 text-muted">
              {segments.length > 0
                ? `${segments.length} audio segment${segments.length === 1 ? "" : "s"} ready`
                : "No listening audio yet"}
            </p>
          </div>
          {canStart && (
            <button
              type="button"
              disabled={acting}
              onClick={() => void startAudio()}
              className="min-h-12 rounded-xl bg-accent px-6 py-3 font-semibold text-white shadow-sm hover:bg-accent-dark disabled:opacity-60"
            >
              {acting
                ? "Starting…"
                : bookAudio.processing_status === "text_ready"
                  ? "Create listening audio"
                  : "Continue creating audio"}
            </button>
          )}
        </div>

        {bookAudio.processing_status === "generating_audio" &&
          bookAudio.processing_active && (
            <p className="mt-4 rounded-xl border border-[#d2c69e] bg-[#fff9e8] p-4 text-[#6d5a22]">
              Echo is creating local mock audio. This page will update shortly.
            </p>
          )}
        {bookAudio.processing_status === "generating_audio" &&
          !bookAudio.processing_active && (
            <p className="mt-4 rounded-xl border border-[#d2c69e] bg-[#fff9e8] p-4 text-[#6d5a22]">
              Audio creation appears to have stopped. Continue to resume it.
            </p>
          )}
        {bookAudio.processing_status !== "text_ready" &&
          bookAudio.processing_status !== "generating_audio" &&
          bookAudio.processing_status !== "ready" && (
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

      {currentSegment && (
        <section className="mt-7 rounded-3xl border border-border bg-surface p-6 sm:p-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-2xl font-semibold">
                Segment {currentSegment.segment_number}
              </h2>
              <p className="mt-1 text-sm text-muted">
                {currentSegment.page_number
                  ? `From page ${currentSegment.page_number}`
                  : "From prepared text"}
              </p>
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
            src={audioFileUrl(currentSegment.audio_url ?? "")}
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
              Previous segment
            </button>
            <button
              type="button"
              disabled={currentIndex >= segments.length - 1}
              onClick={() => moveTo(currentIndex + 1)}
              className="min-h-11 rounded-lg border border-border px-4 font-semibold hover:bg-[#f8f6f0] disabled:opacity-50"
            >
              Next segment
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
              Finished this book.
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

      {segments.length > 1 && (
        <section className="mt-7 rounded-3xl border border-border bg-surface p-6 sm:p-8">
          <h2 className="text-2xl font-semibold">Audio segments</h2>
          <ol className="mt-5 space-y-3">
            {segments.map((segment, index) => (
              <li key={segment.id}>
                <button
                  type="button"
                  onClick={() => moveTo(index)}
                  className={`min-h-12 w-full rounded-xl border px-4 text-left font-semibold ${
                    index === currentIndex
                      ? "border-accent bg-[#edf4f7] text-accent"
                      : "border-border bg-white hover:bg-[#f8f6f0]"
                  }`}
                >
                  Segment {segment.segment_number}
                  {segment.page_number ? ` · page ${segment.page_number}` : ""}
                </button>
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}
