"use client";

import { useCallback, useEffect, useState } from "react";

import { getBook, retryPageText, startTextProcessing } from "@/lib/api";
import type {
  BookDetail,
  BookProcessingStatus,
  PageProcessingStatus,
} from "@/types/books";


const bookStatusLabels: Record<BookProcessingStatus, string> = {
  uploaded: "Ready to read the page text",
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
]);

export function BookProcessing({ bookId }: { bookId: string }) {
  const [book, setBook] = useState<BookDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const nextBook = await getBook(bookId);
      setBook(nextBook);
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Echo could not load this temporary book.",
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

  async function start() {
    setActing(true);
    setError(null);
    try {
      await startTextProcessing(bookId);
      await refresh();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Echo could not start preparing the page text.",
      );
    } finally {
      setActing(false);
    }
  }

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

  if (loading) {
    return <p className="mt-10 text-lg text-muted">Loading your book…</p>;
  }

  if (!book) {
    return (
      <div className="mt-10 rounded-2xl border border-[#d9b9b4] bg-[#fff3f1] p-5">
        <p role="alert" className="text-[#783a33]">
          {error || "Echo could not load this temporary book."}
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
  const canStart =
    book.processing_status === "uploaded" ||
    (isActive && !book.processing_active);
  const percent = Math.round((book.completed_pages / book.total_pages) * 100);

  return (
    <div className="mt-8">
      <section className="rounded-3xl border border-border bg-surface p-6 shadow-[0_20px_60px_rgba(48,55,61,0.06)] sm:p-8">
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div>
            <p className="text-sm font-bold tracking-[0.14em] text-accent uppercase">
              {bookStatusLabels[book.processing_status]}
            </p>
            <h1 className="mt-2 text-3xl font-semibold tracking-[-0.02em] sm:text-4xl">
              {book.title}
            </h1>
            <p className="mt-2 text-muted">
              {book.completed_pages} of {book.total_pages} pages ready
            </p>
          </div>
          {canStart && (
            <button
              type="button"
              disabled={acting}
              onClick={() => void start()}
              className="min-h-12 rounded-xl bg-accent px-6 py-3 font-semibold text-white shadow-sm hover:bg-accent-dark disabled:opacity-60"
            >
              {acting
                ? "Starting…"
                : book.processing_status === "uploaded"
                  ? "Read the page text"
                  : "Continue preparing text"}
            </button>
          )}
        </div>

        <div className="mt-7 h-3 overflow-hidden rounded-full bg-[#e7e5dd]">
          <div
            className="h-full rounded-full bg-accent transition-[width]"
            style={{ width: `${percent}%` }}
            role="progressbar"
            aria-label="Pages with text ready"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={percent}
          />
        </div>

        {isActive && book.processing_active && (
          <p className="mt-4 text-sm text-muted" aria-live="polite">
            Echo is working through your pages in order. You can keep this page open
            to watch the progress.
          </p>
        )}
        {isActive && !book.processing_active && (
          <p className="mt-2 text-sm text-muted">
            Preparation appears to have stopped. Continue to resume from the first
            unfinished page.
          </p>
        )}
        {book.processing_status === "text_ready" && (
          <p className="mt-4 rounded-xl border border-[#a9c5b3] bg-[#f4faf5] p-4 text-[#376247]">
            All page text is prepared. Audio comes in the next milestones.
          </p>
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
        <h2 className="text-2xl font-semibold">Book pages</h2>
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
