"use client";

import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  type DragEndEvent,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  rectSortingStrategy,
  sortableKeyboardCoordinates,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
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
  removePreparedPage,
  reorderPreparedPages,
  retryPageText,
  rotatePreparedPage,
  startTextProcessing,
  updatePageText,
  updatePreparedPageCrop,
} from "@/lib/api";
import type {
  DocumentDetail,
  DocumentPageDetail,
  DocumentProcessingStatus,
  PageCrop,
  PageCropResult,
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

function cropFromPage(page: DocumentPageDetail): PageCrop {
  return {
    crop_left: page.crop_left ?? 0,
    crop_top: page.crop_top ?? 0,
    crop_right: page.crop_right ?? 1,
    crop_bottom: page.crop_bottom ?? 1,
  };
}

function fullCrop(): PageCrop {
  return { crop_left: 0, crop_top: 0, crop_right: 1, crop_bottom: 1 };
}

function composeCrop(baseCrop: PageCrop, localCrop: PageCrop): PageCrop {
  const baseWidth = baseCrop.crop_right - baseCrop.crop_left;
  const baseHeight = baseCrop.crop_bottom - baseCrop.crop_top;
  return {
    crop_left: cropFixed(baseCrop.crop_left + localCrop.crop_left * baseWidth),
    crop_top: cropFixed(baseCrop.crop_top + localCrop.crop_top * baseHeight),
    crop_right: cropFixed(baseCrop.crop_left + localCrop.crop_right * baseWidth),
    crop_bottom: cropFixed(baseCrop.crop_top + localCrop.crop_bottom * baseHeight),
  };
}

function clampCropValue(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.min(1, Math.max(0, value));
}

function cropPercent(value: number): number {
  return Math.round(value * 100);
}

function cropFixed(value: number): number {
  return Number(value.toFixed(4));
}

function versionedImageUrl(url: string, version: number): string {
  return `${url}${url.includes("?") ? "&" : "?"}v=${version}`;
}

function PreparedPageReviewCard({
  documentId,
  page,
  pageCount,
  imageVersion,
  acting,
  accessToken,
  onRotate,
  onRemove,
  onPageCropped,
}: {
  documentId: string;
  page: DocumentPageDetail;
  pageCount: number;
  imageVersion: number;
  acting: boolean;
  accessToken: string | null;
  onRotate: (pageNumber: number, direction: "left" | "right") => void;
  onRemove: (pageNumber: number) => void;
  onPageCropped: (result: PageCropResult) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: page.id });
  const frameRef = useRef<HTMLDivElement>(null);
  const [editing, setEditing] = useState(false);
  const [baseCrop, setBaseCrop] = useState<PageCrop>(() => cropFromPage(page));
  const [crop, setCrop] = useState<PageCrop>(() => fullCrop());
  const [imageSize, setImageSize] = useState<{ width: number; height: number } | null>(
    null,
  );
  const [displayRect, setDisplayRect] = useState<{
    left: number;
    top: number;
    width: number;
    height: number;
  } | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const preparedImageSrc = preparedPageImageUrl(
    documentId,
    page.page_number,
    accessToken,
  );
  const imageSrc = versionedImageUrl(preparedImageSrc, imageVersion);
  const cropWidth = crop.crop_right - crop.crop_left;
  const cropHeight = crop.crop_bottom - crop.crop_top;
  const cropIsValid = cropWidth > 0.02 && cropHeight > 0.02;

  const refreshDisplayRect = useCallback(() => {
    const frame = frameRef.current;
    if (!frame || !imageSize) {
      setDisplayRect(null);
      return;
    }
    const frameWidth = frame.clientWidth;
    const frameHeight = frame.clientHeight;
    if (frameWidth <= 0 || frameHeight <= 0) {
      setDisplayRect(null);
      return;
    }
    const imageRatio = imageSize.width / imageSize.height;
    const frameRatio = frameWidth / frameHeight;
    const renderedWidth = frameRatio > imageRatio ? frameHeight * imageRatio : frameWidth;
    const renderedHeight =
      frameRatio > imageRatio ? frameHeight : frameWidth / imageRatio;
    setDisplayRect({
      left: (frameWidth - renderedWidth) / 2,
      top: (frameHeight - renderedHeight) / 2,
      width: renderedWidth,
      height: renderedHeight,
    });
  }, [imageSize]);

  useEffect(() => {
    refreshDisplayRect();
  }, [refreshDisplayRect]);

  useEffect(() => {
    window.addEventListener("resize", refreshDisplayRect);
    return () => window.removeEventListener("resize", refreshDisplayRect);
  }, [refreshDisplayRect]);

  function normalizedPointerPosition(event: React.PointerEvent<HTMLElement>) {
    const frame = frameRef.current;
    const rect = displayRect;
    if (!frame || !rect) return null;
    const frameBounds = frame.getBoundingClientRect();
    return {
      x: clampCropValue((event.clientX - frameBounds.left - rect.left) / rect.width),
      y: clampCropValue((event.clientY - frameBounds.top - rect.top) / rect.height),
    };
  }

  function moveCrop(event: React.PointerEvent<HTMLElement>) {
    const start = normalizedPointerPosition(event);
    if (!start) return;
    const dragStart = start;
    const startCrop = crop;
    event.currentTarget.setPointerCapture(event.pointerId);

    function onPointerMove(moveEvent: PointerEvent) {
      const frame = frameRef.current;
      const rect = displayRect;
      if (!frame || !rect) return;
      const frameBounds = frame.getBoundingClientRect();
      const nextX = clampCropValue(
        (moveEvent.clientX - frameBounds.left - rect.left) / rect.width,
      );
      const nextY = clampCropValue(
        (moveEvent.clientY - frameBounds.top - rect.top) / rect.height,
      );
      const width = startCrop.crop_right - startCrop.crop_left;
      const height = startCrop.crop_bottom - startCrop.crop_top;
      const left = clampCropValue(startCrop.crop_left + nextX - dragStart.x);
      const top = clampCropValue(startCrop.crop_top + nextY - dragStart.y);
      setError(null);
      setCrop({
        crop_left: cropFixed(Math.min(left, 1 - width)),
        crop_top: cropFixed(Math.min(top, 1 - height)),
        crop_right: cropFixed(Math.min(left, 1 - width) + width),
        crop_bottom: cropFixed(Math.min(top, 1 - height) + height),
      });
    }

    function onPointerUp() {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    }

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp, { once: true });
  }

  function resizeCrop(
    corner: "top-left" | "top-right" | "bottom-left" | "bottom-right",
    event: React.PointerEvent<HTMLButtonElement>,
  ) {
    event.stopPropagation();
    const startCrop = crop;
    event.currentTarget.setPointerCapture(event.pointerId);

    function onPointerMove(moveEvent: PointerEvent) {
      const frame = frameRef.current;
      const rect = displayRect;
      if (!frame || !rect) return;
      const frameBounds = frame.getBoundingClientRect();
      const nextX = clampCropValue(
        (moveEvent.clientX - frameBounds.left - rect.left) / rect.width,
      );
      const nextY = clampCropValue(
        (moveEvent.clientY - frameBounds.top - rect.top) / rect.height,
      );
      const minimum = 0.02;
      const nextCrop = { ...startCrop };
      if (corner.includes("left")) {
        nextCrop.crop_left = Math.min(nextX, startCrop.crop_right - minimum);
      }
      if (corner.includes("right")) {
        nextCrop.crop_right = Math.max(nextX, startCrop.crop_left + minimum);
      }
      if (corner.includes("top")) {
        nextCrop.crop_top = Math.min(nextY, startCrop.crop_bottom - minimum);
      }
      if (corner.includes("bottom")) {
        nextCrop.crop_bottom = Math.max(nextY, startCrop.crop_top + minimum);
      }
      setError(null);
      setCrop({
        crop_left: cropFixed(clampCropValue(nextCrop.crop_left)),
        crop_top: cropFixed(clampCropValue(nextCrop.crop_top)),
        crop_right: cropFixed(clampCropValue(nextCrop.crop_right)),
        crop_bottom: cropFixed(clampCropValue(nextCrop.crop_bottom)),
      });
    }

    function onPointerUp() {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    }

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp, { once: true });
  }

  async function saveCrop() {
    if (!cropIsValid) {
      setError("Choose a larger crop area before saving.");
      return;
    }

    await saveCropArea(composeCrop(baseCrop, crop));
  }

  async function restoreOriginalCrop() {
    await saveCropArea(fullCrop());
  }

  async function saveCropArea(nextCrop: PageCrop) {
    setSaving(true);
    setError(null);
    try {
      const saved = await updatePreparedPageCrop(
        documentId,
        page.page_number,
        nextCrop,
      );
      setBaseCrop({
        crop_left: saved.crop_left,
        crop_top: saved.crop_top,
        crop_right: saved.crop_right,
        crop_bottom: saved.crop_bottom,
      });
      setCrop(fullCrop());
      setEditing(false);
      onPageCropped(saved);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Echo could not save the crop.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`overflow-hidden rounded-2xl border bg-white ${isDragging ? "z-10 border-accent opacity-80" : "border-border"}`}
    >
      <div ref={frameRef} className="relative aspect-[3/4] overflow-hidden bg-[#eeece5]">
        <Image
          src={imageSrc}
          alt={`Prepared preview of page ${page.page_number}`}
          fill
          unoptimized
          className="object-contain"
          onLoad={(event) => {
            setImageSize({
              width: event.currentTarget.naturalWidth,
              height: event.currentTarget.naturalHeight,
            });
          }}
        />
        {editing && displayRect && (
          <div
            className="absolute bg-[#17202a66]"
            style={{
              left: displayRect.left,
              top: displayRect.top,
              width: displayRect.width,
              height: displayRect.height,
            }}
          >
            <div
              role="group"
              aria-label={`Crop area for page ${page.page_number}`}
              onPointerDown={moveCrop}
              className={`absolute touch-none cursor-move border-2 ${cropIsValid ? "border-white" : "border-[#d95043]"} bg-white/15 shadow-[0_0_0_9999px_rgba(23,32,42,0.35)]`}
              style={{
                left: `${cropPercent(crop.crop_left)}%`,
                top: `${cropPercent(crop.crop_top)}%`,
                width: `${cropPercent(cropWidth)}%`,
                height: `${cropPercent(cropHeight)}%`,
              }}
            >
              {(
                [
                  ["top-left", "top-0 left-0 -translate-x-1/2 -translate-y-1/2 cursor-nwse-resize"],
                  ["top-right", "top-0 right-0 translate-x-1/2 -translate-y-1/2 cursor-nesw-resize"],
                  ["bottom-left", "bottom-0 left-0 -translate-x-1/2 translate-y-1/2 cursor-nesw-resize"],
                  ["bottom-right", "right-0 bottom-0 translate-x-1/2 translate-y-1/2 cursor-nwse-resize"],
                ] as const
              ).map(([corner, positionClass]) => (
                <button
                  key={corner}
                  type="button"
                  aria-label={`Resize ${corner} crop corner`}
                  onPointerDown={(event) => resizeCrop(corner, event)}
                  className={`absolute size-5 rounded-full border-2 border-white bg-accent shadow ${positionClass}`}
                />
              ))}
            </div>
          </div>
        )}
      </div>
      <div className="p-4 text-sm">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="font-semibold">Page {page.page_number}</p>
            {page.original_filename ? (
              <p className="mt-1 truncate text-muted" title={page.original_filename}>
                {page.original_filename}
              </p>
            ) : (
              <p className="mt-1 text-muted">PDF page requiring text reading</p>
            )}
          </div>
          <button
            type="button"
            disabled={acting || saving}
            onClick={() => {
              setBaseCrop(cropFromPage(page));
              setCrop(fullCrop());
              setError(null);
              setEditing((current) => !current);
            }}
            className="shrink-0 rounded-lg border border-border px-3 py-2 font-semibold hover:bg-[#f4f1e9] disabled:opacity-60"
          >
            {editing ? "Close" : "Crop"}
          </button>
        </div>

        <div className="mt-4 grid grid-cols-[2.75rem_1fr_1fr] gap-2">
          <button
            type="button"
            disabled={acting || saving}
            className="inline-flex min-h-11 cursor-grab items-center justify-center rounded-lg border border-border hover:bg-[#f4f1e9] disabled:cursor-not-allowed disabled:opacity-60 active:cursor-grabbing"
            aria-label={`Drag page ${page.page_number} to reorder`}
            title="Drag to reorder"
            {...attributes}
            {...listeners}
          >
            <span aria-hidden="true" className="grid grid-cols-3 gap-1">
              {Array.from({ length: 9 }, (_, index) => (
                <span key={index} className="size-1 rounded-full bg-muted" />
              ))}
            </span>
          </button>
          <button
            type="button"
            disabled={acting || saving}
            onClick={() => onRotate(page.page_number, "left")}
            className="rounded-lg border border-border px-3 py-2 font-semibold hover:bg-[#f4f1e9] disabled:opacity-60"
          >
            Rotate left
          </button>
          <button
            type="button"
            disabled={acting || saving}
            onClick={() => onRotate(page.page_number, "right")}
            className="rounded-lg border border-border px-3 py-2 font-semibold hover:bg-[#f4f1e9] disabled:opacity-60"
          >
            Rotate right
          </button>
        </div>
        <button
          type="button"
          disabled={acting || saving || pageCount <= 1}
          onClick={() => onRemove(page.page_number)}
          className="mt-2 w-full rounded-lg border border-[#d9b9b4] px-3 py-2 font-semibold text-[#783a33] hover:bg-[#fff3f1] disabled:opacity-60"
        >
          Remove page
        </button>

        {editing && (
          <div className="mt-4 space-y-3">
            <p className="text-muted">
              Drag the box to move it. Drag a corner to resize it.
            </p>
            <div className="flex flex-wrap gap-2 pt-1">
              <button
                type="button"
                disabled={saving || !cropIsValid}
                onClick={() => void saveCrop()}
                className="rounded-lg bg-accent px-4 py-2 font-semibold text-white hover:bg-accent-dark disabled:opacity-60"
              >
                {saving ? "Saving..." : "Save crop"}
              </button>
              <button
                type="button"
                disabled={saving}
                onClick={() => void restoreOriginalCrop()}
                className="rounded-lg border border-border px-4 py-2 font-semibold hover:bg-[#f4f1e9] disabled:opacity-60"
              >
                Restore original
              </button>
              <button
                type="button"
                disabled={saving}
                onClick={() => {
                  setCrop(fullCrop());
                  setError(null);
                }}
                className="rounded-lg border border-border px-4 py-2 font-semibold hover:bg-[#f4f1e9] disabled:opacity-60"
              >
                Reset
              </button>
            </div>
            {error && (
              <p role="alert" className="rounded-lg bg-[#fff3f1] p-3 text-[#783a33]">
                {error}
              </p>
            )}
          </div>
        )}
      </div>
    </li>
  );
}

export function DocumentProcessing({ documentId }: { documentId: string }) {
  const { session } = useAuthSession();
  const accessToken = session?.access_token ?? null;
  const router = useRouter();
  const [document, setDocument] = useState<DocumentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [audioProgress, setAudioProgress] = useState({ completed: 0, total: 0 });
  const [editingPageNumber, setEditingPageNumber] = useState<number | null>(null);
  const [editingText, setEditingText] = useState("");
  const [reviewImageVersion, setReviewImageVersion] = useState(0);
  const [imageVersionsByPage, setImageVersionsByPage] = useState<Record<string, number>>(
    {},
  );
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );
  const embeddedTextStartRequestedRef = useRef(false);
  const documentLoadedRef = useRef(false);
  const audioProgressFailureCountRef = useRef(0);

  const refresh = useCallback(async () => {
    try {
      const nextDocument = await getDocument(documentId);
      documentLoadedRef.current = true;
      setDocument(nextDocument);
      setError(null);
    } catch (caught) {
      embeddedTextStartRequestedRef.current = false;
      if (!documentLoadedRef.current) {
        setError(
          caught instanceof Error
            ? caught.message
            : "Echo could not load this temporary document.",
        );
      }
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
    const timer = window.setInterval(() => void refresh(), 3000);
    return () => window.clearInterval(timer);
  }, [document, refresh]);

  const refreshAudioProgress = useCallback(async () => {
    try {
      const audio = await getDocumentAudio(documentId);
      const completed = audio.segments.filter(
        (segment) => segment.processing_status === "completed" && segment.audio_url,
      ).length;
      audioProgressFailureCountRef.current = 0;
      setAudioProgress({ completed, total: audio.segments.length });
    } catch (caught) {
      audioProgressFailureCountRef.current += 1;
      if (audioProgressFailureCountRef.current >= 3) {
        setError(
          caught instanceof Error
            ? caught.message
            : "Echo could not load the listening audio progress.",
        );
      }
    }
  }, [documentId]);

  useEffect(() => {
    if (!document || document.processing_status !== "generating_audio") return;

    const initialTimer = window.setTimeout(() => void refreshAudioProgress(), 0);
    if (!document.processing_active) {
      return () => window.clearTimeout(initialTimer);
    }

    const timer = window.setInterval(() => void refreshAudioProgress(), 3000);
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

  const savePageText = useCallback(async () => {
    if (editingPageNumber === null) return;
    setActing(true);
    setError(null);
    try {
      const nextDocument = await updatePageText(
        documentId,
        editingPageNumber,
        editingText,
      );
      setDocument(nextDocument);
      setEditingPageNumber(null);
      setEditingText("");
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : `Echo could not save page ${editingPageNumber} text.`,
      );
    } finally {
      setActing(false);
    }
  }, [documentId, editingPageNumber, editingText]);

  const rotatePage = useCallback(
    async (pageNumber: number, direction: "left" | "right") => {
      setActing(true);
      setError(null);
      try {
        const nextDocument = await rotatePreparedPage(documentId, pageNumber, direction);
        setDocument(nextDocument);
        setImageVersionsByPage((current) => ({
          ...current,
          [String(pageNumber)]: (current[String(pageNumber)] ?? 0) + 1,
        }));
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : `Echo could not rotate page ${pageNumber}.`,
        );
      } finally {
        setActing(false);
      }
    },
    [documentId],
  );

  const handleReviewDragEnd = useCallback(
    async (event: DragEndEvent) => {
      const { active, over } = event;
      if (!document || !over || active.id === over.id) return;
      const orderedPages = [...document.pages].sort(
        (left, right) => left.page_number - right.page_number,
      );
      const oldIndex = orderedPages.findIndex((page) => page.id === active.id);
      const newIndex = orderedPages.findIndex((page) => page.id === over.id);
      if (oldIndex < 0 || newIndex < 0) return;
      const nextPages = arrayMove(orderedPages, oldIndex, newIndex);

      setActing(true);
      setError(null);
      try {
        const nextDocument = await reorderPreparedPages(
          documentId,
          nextPages.map((page) => page.id),
        );
        setDocument(nextDocument);
        setReviewImageVersion((current) => current + 1);
      } catch (caught) {
        setError(
          caught instanceof Error ? caught.message : "Echo could not rearrange these pages.",
        );
      } finally {
        setActing(false);
      }
    },
    [document, documentId],
  );

  const removePage = useCallback(
    async (pageNumber: number) => {
      if (!window.confirm(`Remove page ${pageNumber} from this upload?`)) return;
      setActing(true);
      setError(null);
      try {
        const nextDocument = await removePreparedPage(documentId, pageNumber);
        setDocument(nextDocument);
        setReviewImageVersion((current) => current + 1);
        setImageVersionsByPage({});
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : `Echo could not remove page ${pageNumber}.`,
        );
      } finally {
        setActing(false);
      }
    },
    [documentId],
  );

  const applySavedCrop = useCallback((saved: PageCropResult) => {
    setDocument((current) => {
      if (!current) return current;
      return {
        ...current,
        pages: current.pages.map((page) =>
          page.id === saved.page_id
            ? {
                ...page,
                crop_left: saved.crop_left,
                crop_top: saved.crop_top,
                crop_right: saved.crop_right,
                crop_bottom: saved.crop_bottom,
              }
            : page,
        ),
      };
    });
    setImageVersionsByPage((current) => ({
      ...current,
      [String(saved.page_number)]: (current[String(saved.page_number)] ?? 0) + 1,
    }));
  }, []);

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
  const canResumeFailedAudio =
    document.processing_status === "failed" &&
    document.failed_pages === 0 &&
    document.audio_segment_count > 0 &&
    document.pages.every((page) => page.processing_status === "completed");
  const canResumeAudio =
    (document.processing_status === "generating_audio" && !document.processing_active) ||
    canResumeFailedAudio;
  const canStartAudio =
    document.processing_status === "text_ready" || canResumeAudio;
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
    <div className="mt-3">
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
        {canResumeAudio && (
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
        {document.error_message && !error && !canResumeFailedAudio && (
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
              <h2 className="text-2xl font-semibold">Review pages before text reading</h2>
              <p className="mt-2 max-w-2xl text-muted">
                Check page order, rotation, and crop before Echo reads the page text.
              </p>
            </div>
            <p className="text-sm font-semibold text-muted">{ocrPages.length} pages</p>
          </div>
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={(event) => void handleReviewDragEnd(event)}
          >
            <SortableContext
              items={ocrPages.map((page) => page.id)}
              strategy={rectSortingStrategy}
            >
              <ol className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {ocrPages.map((page) => (
                  <PreparedPageReviewCard
                    key={page.id}
                    documentId={document.id}
                    page={page}
                    pageCount={ocrPages.length}
                    imageVersion={
                      reviewImageVersion +
                      (imageVersionsByPage[String(page.page_number)] ?? 0)
                    }
                    acting={acting}
                    accessToken={accessToken}
                    onRotate={(pageNumber, direction) =>
                      void rotatePage(pageNumber, direction)
                    }
                    onRemove={(pageNumber) => void removePage(pageNumber)}
                    onPageCropped={applySavedCrop}
                  />
                ))}
              </ol>
            </SortableContext>
          </DndContext>
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
                <p className="mt-3 rounded-lg border border-[#d2c69e] bg-[#fff9e8] p-3 text-sm text-[#6d5a22]">
                  {page.error_message}
                </p>
              )}
              {page.warning_messages.length > 0 && (
                <div className="mt-3 rounded-lg border border-[#d2c69e] bg-[#fff9e8] p-3 text-sm text-[#6d5a22]">
                  {page.warning_messages.map((message) => (
                    <p key={message}>{message}</p>
                  ))}
                </div>
              )}
              {(page.extracted_text || page.processing_status === "failed") && (
                <details className="mt-4 rounded-xl bg-[#f8f6f0] p-4">
                  <summary className="cursor-pointer font-semibold">
                    {page.extracted_text
                      ? `Review page text (${page.extracted_character_count} characters)`
                      : "Enter page text manually"}
                  </summary>
                  {editingPageNumber === page.page_number ? (
                    <div className="mt-3">
                      <textarea
                        value={editingText}
                        onChange={(event) => setEditingText(event.target.value)}
                        rows={10}
                        className="w-full rounded-lg border border-border bg-white p-3 text-sm leading-7 text-foreground"
                      />
                      <div className="mt-3 flex flex-wrap gap-2">
                        <button
                          type="button"
                          disabled={acting || !editingText.trim()}
                          onClick={() => void savePageText()}
                          className="min-h-10 rounded-lg bg-accent px-4 font-semibold text-white hover:bg-accent-dark disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          Save page text
                        </button>
                        <button
                          type="button"
                          disabled={acting}
                          onClick={() => {
                            setEditingPageNumber(null);
                            setEditingText("");
                          }}
                          className="min-h-10 rounded-lg border border-border px-4 font-semibold hover:bg-white disabled:opacity-60"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                      {page.extracted_text && (
                        <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-muted">
                          {page.extracted_text}
                        </p>
                      )}
                      <button
                        type="button"
                        disabled={acting}
                        onClick={() => {
                          setEditingPageNumber(page.page_number);
                          setEditingText(page.extracted_text);
                        }}
                        className="mt-3 min-h-10 rounded-lg border border-accent px-4 font-semibold text-accent hover:bg-white disabled:opacity-60"
                      >
                        {page.extracted_text ? "Edit page text" : "Enter page text manually"}
                      </button>
                    </>
                  )}
                </details>
              )}
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
