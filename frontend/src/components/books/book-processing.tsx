"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";

import {
  getBook,
  getBookAudio,
  prepareBookAudio,
  retryPageText,
  startTextProcessing,
} from "@/lib/api";
import type {
  BookDetail,
  BookProcessingStatus,
  PageProcessingStatus,
} from "@/types/books";


const bookStatusLabels: Record<BookProcessingStatus, string> = {
  uploaded: "Ready to create listening audio",
  normalizing_pages: "Preparing the pages",
  inspecting: "Checking the pages",
  extracting_text: "Reading the page text",
  running_ocr: "Reading the page text",
  text_ready: "Page text ready",
  generating_audio: "Creating the audio",
  ready: "Ready",
  failed: "Some pages need attention",
};

const pageStatusLabels: Record<PageProcessingStatus, string> = {
  pending: "Waiting",
  normalizing: "Preparing the page",
  extracting: "Reading the page text",
  running_ocr: "Reading the page text",
  completed: "Text ready",
  failed: "Needs another try",
};

const activeStatuses = new Set<BookProcessingStatus>([
  "normalizing_pages",
  "inspecting",
  "extracting_text",
  "running_ocr",
  "generating_audio",
]);

const textProcessingStatuses = new Set<BookProcessingStatus>([
  "normalizing_pages",
  "inspecting",
  "extracting_text",
  "running_ocr",
]);

export function BookProcessing({ bookId }: { bookId: string }) {
  const [book, setBook] = useState<BookDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [creatingListeningAudio, setCreatingListeningAudio] = useState(false);
  const [audioProgress, setAudioProgress] = useState({ completed: 0, total: 0 });
  const audioStartRequestedRef = useRef(false);

  const refresh = useCallback(async () => {
    try {
      const nextBook = await getBook(bookId);
      setBook(nextBook);
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Echo could not load this temporary document.",
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
      !book ||
      !activeStatuses.has(book.processing_status) ||
      !book.processing_active
    ) {
      return;
    }
    const timer = window.setInterval(() => void refresh(), 1500);
    return () => window.clearInterval(timer);
  }, [book, refresh]);

  const refreshAudioProgress = useCallback(async () => {
    const audio = await getBookAudio(bookId);
    const completed = audio.segments.filter(
      (segment) => segment.processing_status === "completed" && segment.audio_url,
    ).length;
    setAudioProgress({ completed, total: audio.segments.length });
  }, [bookId]);

  useEffect(() => {
    if (!book || book.processing_status !== "generating_audio") return;

    const initialTimer = window.setTimeout(() => void refreshAudioProgress(), 0);
    if (!book.processing_active) {
      return () => window.clearTimeout(initialTimer);
    }

    const timer = window.setInterval(() => void refreshAudioProgress(), 1500);
    return () => {
      window.clearTimeout(initialTimer);
      window.clearInterval(timer);
    };
  }, [book, refreshAudioProgress]);

  async function retry(pageNumber: number) {
    setActing(true);
    setError(null);
    try {
      await retryPageText(bookId, pageNumber);
      await refresh();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : `Echo could not retry page ${pageNumber}.`,
      );
    } finally {
      setActing(false);
    }
  }

  const startAudio = useCallback(async () => {
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
      setCreatingListeningAudio(false);
      audioStartRequestedRef.current = false;
    } finally {
      setActing(false);
    }
  }, [bookId, refresh]);

  useEffect(() => {
    if (
      !creatingListeningAudio ||
      !book ||
      book.processing_status !== "text_ready" ||
      audioStartRequestedRef.current
    ) {
      return;
    }

    audioStartRequestedRef.current = true;
    void startAudio();
  }, [book, creatingListeningAudio, startAudio]);

  async function startListeningAudio() {
    setCreatingListeningAudio(true);
    setActing(true);
    setError(null);
    audioStartRequestedRef.current = false;

    try {
      if (book?.processing_status === "text_ready") {
        audioStartRequestedRef.current = true;
        await prepareBookAudio(bookId);
        await refresh();
        return;
      }

      await startTextProcessing(bookId);
      await refresh();
    } catch (caught) {
      setCreatingListeningAudio(false);
      setError(
        caught instanceof Error
          ? caught.message
          : "Echo could not start creating listening audio.",
      );
    } finally {
      setActing(false);
    }
  }

  if (loading) {
    return <p className="mt-10 text-lg text-muted">Loading your document...</p>;
  }

  if (!book) {
    return (
      <div className="mt-10 rounded-2xl border border-[#d9b9b4] bg-[#fff3f1] p-5">
        <p role="alert" className="text-[#783a33]">
          {error || "Echo could not load this temporary document."}
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

  const isActive = activeStatuses.has(book.processing_status);
  const canStartText =
    book.processing_status === "uploaded" ||
    (textProcessingStatuses.has(book.processing_status) && !book.processing_active);
  const audioPercent =
    audioProgress.total > 0
      ? Math.round((audioProgress.completed / audioProgress.total) * 100)
      : 0;
  const progressPercent =
    book.processing_status === "ready" ? 100 : book.processing_status === "generating_audio" ? audioPercent : 0;
  const progressLabel =
    book.processing_status === "generating_audio"
      ? `${audioProgress.completed} of ${audioProgress.total || "…"} audio parts ready`
      : `${book.completed_pages} of ${book.total_pages} pages ready`;

  return (
    <div className="mt-8">
      <section className="rounded-2xl border border-border bg-surface p-5 shadow-[0_14px_40px_rgba(48,55,61,0.05)] sm:p-6">
        <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-bold tracking-[0.12em] text-accent uppercase">
              {bookStatusLabels[book.processing_status]}
            </p>
            <h1 className="mt-2 text-3xl font-semibold sm:text-4xl">
              {book.title}
            </h1>
            <p className="mt-1 text-muted">{progressLabel}</p>
          </div>
          {canStartText && (
            <button
              type="button"
              disabled={acting}
              onClick={() => void startListeningAudio()}
              className="min-h-12 rounded-xl bg-accent px-6 py-3 font-semibold text-white shadow-sm hover:bg-accent-dark disabled:opacity-60"
            >
              {acting ? "Starting audio..." : "Create listening audio"}
            </button>
          )}
        </div>

        <div className="mt-7 h-3 overflow-hidden rounded-full bg-[#e7e5dd]">
          <div
            className="h-full rounded-full bg-accent transition-[width]"
            style={{ width: `${progressPercent}%` }}
            role="progressbar"
            aria-label="Audio preparation progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progressPercent}
          />
        </div>

        {isActive && book.processing_active && (
          <p className="mt-4 text-sm text-muted" aria-live="polite">
            {book.processing_status === "generating_audio"
              ? "Echo is creating listening audio. You can keep this page open to watch the progress."
              : "Echo is working through your pages in order. You can keep this page open to watch the progress."}
          </p>
        )}
        {textProcessingStatuses.has(book.processing_status) && !book.processing_active && (
          <p className="mt-2 text-sm text-muted">
            Preparation appears to have stopped. Continue to resume from the first
            unfinished page.
          </p>
        )}
        {book.processing_status === "text_ready" && (
          <div className="mt-4 rounded-xl border border-[#a9c5b3] bg-[#f4faf5] p-4 text-[#376247]">
            <p>All page text is prepared. You can now create listening audio.</p>
            <button
              type="button"
              disabled={acting}
              onClick={() => void startListeningAudio()}
              className="mt-3 min-h-11 rounded-lg bg-accent px-4 font-semibold text-white hover:bg-accent-dark disabled:opacity-60"
            >
              {acting ? "Starting audio..." : "Create listening audio"}
            </button>
          </div>
        )}
        {book.processing_status === "generating_audio" && !book.processing_active && (
          <div className="mt-4 rounded-xl border border-[#d9b9b4] bg-[#fff3f1] p-4 text-[#783a33]">
            <p>Audio preparation stopped before it finished.</p>
            <button
              type="button"
              disabled={acting}
              onClick={() => void startListeningAudio()}
              className="mt-3 min-h-11 rounded-lg border border-[#d9b9b4] px-4 font-semibold hover:bg-white disabled:opacity-60"
            >
              {acting ? "Starting audio..." : "Resume audio preparation"}
            </button>
          </div>
        )}
        {book.processing_status === "ready" && (
          <div className="mt-4 rounded-xl border border-[#a9c5b3] bg-[#f4faf5] p-4 text-[#376247]">
            <p>Listening audio is ready.</p>
            <Link
              href={`/books/${book.id}/listen`}
              className="mt-3 inline-flex min-h-11 items-center rounded-lg bg-accent px-4 font-semibold text-white hover:bg-accent-dark"
            >
              Listen now
            </Link>
          </div>
        )}
        {book.error_message && !error && (
          <p className="mt-4 rounded-xl border border-[#d9b9b4] bg-[#fff3f1] p-4 text-[#783a33]">
            {book.error_message}
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

      <section className="mt-7 rounded-3xl border border-border bg-surface p-6 sm:p-8">
        <h2 className="text-2xl font-semibold">Upload pages</h2>
        <ol className="mt-5 space-y-3">
          {book.pages.map((page) => (
            <li key={page.id} className="rounded-2xl border border-border bg-white p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="font-semibold">
                    Page {page.page_number}
                    {page.original_filename ? ` · ${page.original_filename}` : ""}
                  </h3>
                  <p className="mt-1 text-sm text-muted">
                    {pageStatusLabels[page.processing_status]}
                  </p>
                </div>
                {page.processing_status === "failed" && (
                  <button
                    type="button"
                    disabled={acting}
                    onClick={() => void retry(page.page_number)}
                    className="min-h-11 rounded-lg border border-accent px-4 font-semibold text-accent hover:bg-[#edf4f7] disabled:opacity-60"
                  >
                    Try this page again
                  </button>
                )}
              </div>
              {page.error_message && (
                <p className="mt-3 text-sm text-[#783a33]">{page.error_message}</p>
              )}
              {page.extracted_text && (
                <details className="mt-4 rounded-xl bg-[#f8f6f0] p-4">
                  <summary className="cursor-pointer font-semibold">
                    Review page text ({page.extracted_character_count} characters)
                  </summary>
                  <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-muted">
                    {page.extracted_text}
                  </p>
                </details>
              )}
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
