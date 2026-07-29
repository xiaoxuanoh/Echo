"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { useAuthSession } from "@/components/auth/use-auth-session";
import {
  deleteDocumentRecording,
  getDocument,
  getDocumentAudio,
  prepareDocumentAudio,
  preparedPageImageUrl,
  retryPageText,
  startTextProcessing,
} from "@/lib/api";
import type {
  DocumentDetail,
  DocumentProcessingStatus,
  PageProcessingStatus,
} from "@/types/documents";


const documentStatusLabels: Record<DocumentProcessingStatus, string> = {
  uploaded: "Review prepared pages",
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

const activeStatuses = new Set<DocumentProcessingStatus>([
  "normalizing_pages",
  "inspecting",
  "extracting_text",
  "running_ocr",
  "generating_audio",
]);

const textProcessingStatuses = new Set<DocumentProcessingStatus>([
  "normalizing_pages",
  "inspecting",
  "extracting_text",
  "running_ocr",
]);

export function DocumentProcessing({ documentId }: { documentId: string }) {
  const { session } = useAuthSession();
  const accessToken = session?.access_token ?? null;
  const router = useRouter();
  const [document, setDocument] = useState<DocumentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [audioProgress, setAudioProgress] = useState({ completed: 0, total: 0 });
  const embeddedTextStartRequestedRef = useRef(false);

  const refresh = useCallback(async () => {
    try {
      const nextDocument = await getDocument(documentId);
      setDocument(nextDocument);
      setError(null);
    } catch (caught) {
      embeddedTextStartRequestedRef.current = false;
      setError(
        caught instanceof Error
          ? caught.message
          : "Echo could not load this temporary document.",
      );
    } finally {
      setLoading(false);
    }
  }, [documentId]);

  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  useEffect(() => {
    if (
      !document ||
      !activeStatuses.has(document.processing_status) ||
      !document.processing_active
    ) {
      return;
    }
    const timer = window.setInterval(() => void refresh(), 1500);
    return () => window.clearInterval(timer);
  }, [document, refresh]);

  const refreshAudioProgress = useCallback(async () => {
    const audio = await getDocumentAudio(documentId);
    const completed = audio.segments.filter(
      (segment) => segment.processing_status === "completed" && segment.audio_url,
    ).length;
    setAudioProgress({ completed, total: audio.segments.length });
  }, [documentId]);

  useEffect(() => {
    if (!document || document.processing_status !== "generating_audio") return;

    const initialTimer = window.setTimeout(() => void refreshAudioProgress(), 0);
    if (!document.processing_active) {
      return () => window.clearTimeout(initialTimer);
    }

    const timer = window.setInterval(() => void refreshAudioProgress(), 1500);
    return () => {
      window.clearTimeout(initialTimer);
      window.clearInterval(timer);
    };
  }, [document, refreshAudioProgress]);

  async function retry(pageNumber: number) {
    setActing(true);
    setError(null);
    try {
      await retryPageText(documentId, pageNumber);
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

  const startTextPreparation = useCallback(async () => {
    setActing(true);
    setError(null);
    try {
      await startTextProcessing(documentId);
      await refresh();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Echo could not start reading your pages.",
      );
    } finally {
      setActing(false);
    }
  }, [documentId, refresh]);

  useEffect(() => {
    if (
      !document ||
      document.processing_status !== "uploaded" ||
      document.pages.some((page) => page.extraction_method === "ocr") ||
      embeddedTextStartRequestedRef.current
    ) {
      return;
    }

    embeddedTextStartRequestedRef.current = true;
    void startTextPreparation();
  }, [document, startTextPreparation]);

  const startAudio = useCallback(async () => {
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
  }, [documentId, refresh]);

  const restartUpload = useCallback(async () => {
    if (!document) return;
    if (
      !window.confirm(
        `Restart this upload? Echo will remove "${document.title}" from your library.`,
      )
    ) {
      return;
    }

    setActing(true);
    setError(null);
    try {
      await deleteDocumentRecording(documentId);
      router.push("/books/new");
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Echo could not restart this upload.",
      );
      setActing(false);
    }
  }, [document, documentId, router]);

  if (loading) {
    return <p className="mt-10 text-lg text-muted">Loading your document...</p>;
  }

  if (!document) {
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

  const isActive = activeStatuses.has(document.processing_status);
  const ocrPages = document.pages.filter((page) => page.extraction_method === "ocr");
  const isAwaitingOcrReview =
    document.processing_status === "uploaded" && ocrPages.length > 0;
  const isPreparingText =
    (document.processing_status === "uploaded" && ocrPages.length === 0) ||
    textProcessingStatuses.has(document.processing_status);
  const canResumeText =
    textProcessingStatuses.has(document.processing_status) && !document.processing_active;
  const canStartAudio =
    document.processing_status === "text_ready" ||
    (document.processing_status === "generating_audio" && !document.processing_active);
  const listenNowDisabled = acting || !canStartAudio;
  const audioPercent =
    audioProgress.total > 0
      ? Math.round((audioProgress.completed / audioProgress.total) * 100)
      : 0;
  const textPercent =
    document.total_pages > 0
      ? Math.round((document.completed_pages / document.total_pages) * 100)
      : 0;
  const progressPercent =
    document.processing_status === "ready"
      ? 100
      : document.processing_status === "generating_audio"
        ? audioPercent
        : textPercent;
  const progressLabel =
    document.processing_status === "generating_audio"
      ? `${audioProgress.completed} of ${audioProgress.total || "…"} audio parts ready`
      : `${document.completed_pages} of ${document.total_pages} pages ready`;

  return (
    <div className="mt-8">
      <section className="rounded-2xl border border-border bg-surface p-5 shadow-[0_14px_40px_rgba(48,55,61,0.05)] sm:p-6">
        <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-bold tracking-[0.12em] text-accent uppercase">
              {documentStatusLabels[document.processing_status]}
            </p>
            <h1 className="mt-2 text-3xl font-semibold sm:text-4xl">
              {document.title}
            </h1>
            <p className="mt-1 text-muted">{progressLabel}</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              disabled={acting}
              onClick={() => void restartUpload()}
              className="min-h-12 rounded-xl border border-[#d9b9b4] px-6 py-3 font-semibold text-[#783a33] transition-colors duration-150 hover:bg-[#fff3f1] disabled:cursor-wait disabled:opacity-60"
            >
              {acting ? "Restarting..." : "Restart"}
            </button>
            {document.processing_status === "ready" ? (
              <Link
                href={`/books/${document.id}/listen`}
                className="inline-flex min-h-12 items-center rounded-xl bg-accent px-6 py-3 font-semibold text-white shadow-sm transition-colors duration-150 hover:bg-accent-dark"
              >
                Listen now
              </Link>
            ) : (
              <button
                type="button"
                disabled={listenNowDisabled}
                onClick={() => void startAudio()}
                className="min-h-12 rounded-xl bg-accent px-6 py-3 font-semibold text-white shadow-sm transition-colors duration-150 hover:bg-accent-dark disabled:cursor-not-allowed disabled:border disabled:border-border disabled:bg-[#edf1f0] disabled:text-muted disabled:shadow-none"
                aria-describedby={isPreparingText ? "listen-now-waiting" : undefined}
              >
                Listen now
              </button>
            )}
          </div>
        </div>

        <div className="mt-7 h-3 overflow-hidden rounded-full bg-[#e7e5dd]">
          <div
            className="h-full rounded-full bg-accent transition-[width]"
            style={{ width: `${progressPercent}%` }}
            role="progressbar"
            aria-label="Document preparation progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progressPercent}
          />
        </div>

        {isPreparingText && (
          <p id="listen-now-waiting" className="mt-4 text-sm text-muted" aria-live="polite">
            Echo is reading your pages first. Listen now will unlock when the text is ready.
          </p>
        )}
        {isAwaitingOcrReview && (
          <div className="mt-4 rounded-xl border border-[#b9d0da] bg-[#edf4f7] p-4 text-[#28516a]">
            <p>
              Review the prepared page images below before Echo reads the page text.
            </p>
            <button
              type="button"
              disabled={acting}
              onClick={() => void startTextPreparation()}
              className="mt-3 min-h-11 rounded-lg bg-accent px-4 font-semibold text-white transition-colors duration-150 hover:bg-accent-dark disabled:cursor-wait disabled:opacity-60"
            >
              {acting ? "Starting..." : "Start reading page text"}
            </button>
          </div>
        )}
        {isActive && document.processing_active && (
          <p className="mt-4 text-sm text-muted" aria-live="polite">
            {document.processing_status === "generating_audio"
              ? "Echo is creating listening audio. You can keep this page open to watch the progress."
              : "Echo is working through your pages in order. You can keep this page open to watch the progress."}
          </p>
        )}
        {canResumeText && (
          <div className="mt-4 rounded-xl border border-[#d9b9b4] bg-[#fff3f1] p-4 text-[#783a33]">
            <p>
              Preparation appears to have stopped. Resume reading from the first
              unfinished page.
            </p>
            <button
              type="button"
              disabled={acting}
              onClick={() => void startTextPreparation()}
              className="mt-3 min-h-11 rounded-lg border border-[#d9b9b4] px-4 font-semibold transition-colors duration-150 hover:bg-white disabled:opacity-60"
            >
              Resume reading pages
            </button>
          </div>
        )}
        {document.processing_status === "text_ready" && (
          <div className="mt-4 rounded-xl border border-[#a9c5b3] bg-[#f4faf5] p-4 text-[#376247]">
            <p>All page text is prepared. Select Listen now to create listening audio.</p>
          </div>
        )}
        {document.processing_status === "generating_audio" && !document.processing_active && (
          <div className="mt-4 rounded-xl border border-[#d9b9b4] bg-[#fff3f1] p-4 text-[#783a33]">
            <p>Audio preparation stopped before it finished.</p>
            <button
              type="button"
              disabled={acting}
              onClick={() => void startAudio()}
              className="mt-3 min-h-11 rounded-lg border border-[#d9b9b4] px-4 font-semibold transition-colors duration-150 hover:bg-white disabled:opacity-60"
            >
              {acting ? "Starting audio..." : "Resume audio preparation"}
            </button>
          </div>
        )}
        {document.processing_status === "ready" && (
          <div className="mt-4 rounded-xl border border-[#a9c5b3] bg-[#f4faf5] p-4 text-[#376247]">
            <p>Listening audio is ready.</p>
          </div>
        )}
        {document.error_message && !error && (
          <p className="mt-4 rounded-xl border border-[#d9b9b4] bg-[#fff3f1] p-4 text-[#783a33]">
            {document.error_message}
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

      {isAwaitingOcrReview && ocrPages.length > 0 && (
        <section className="mt-7 rounded-3xl border border-border bg-surface p-6 sm:p-8">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-2xl font-semibold">Preview pages before OCR</h2>
              <p className="mt-2 max-w-2xl text-muted">
                These are the prepared page images Echo will read. Check that rotation,
                crop, and page order look right before starting OCR.
              </p>
            </div>
            <p className="text-sm font-semibold text-muted">{ocrPages.length} pages</p>
          </div>
          <ol className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {ocrPages.map((page) => (
              <li
                key={page.id}
                className="overflow-hidden rounded-2xl border border-border bg-white"
              >
                <div className="relative aspect-[3/4] bg-[#eeece5]">
                  <Image
                    src={preparedPageImageUrl(
                      document.id,
                      page.page_number,
                      accessToken,
                    )}
                    alt={`Prepared preview of page ${page.page_number}`}
                    fill
                    unoptimized
                    className="object-contain"
                  />
                </div>
                <div className="p-4 text-sm">
                  <p className="font-semibold">Page {page.page_number}</p>
                  {page.original_filename ? (
                    <p className="mt-1 truncate text-muted" title={page.original_filename}>
                      {page.original_filename}
                    </p>
                  ) : (
                    <p className="mt-1 text-muted">PDF page requiring OCR</p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}

      <section className="mt-7 rounded-3xl border border-border bg-surface p-6 sm:p-8">
        <h2 className="text-2xl font-semibold">Upload pages</h2>
        <ol className="mt-5 space-y-3">
          {document.pages.map((page) => (
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
