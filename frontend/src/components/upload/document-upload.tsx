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
import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import {
  assignDocumentToFolder,
  getDocumentLibrary,
  renameDocumentFolder,
  uploadImages,
  uploadPdf,
} from "@/lib/api";
import {
  defaultListeningLanguage,
  isListeningLanguage,
  listeningLanguageLabel,
  listeningLanguages,
  type ListeningLanguage,
} from "@/lib/listening-languages";
import { validateNewImages, validatePdf } from "@/lib/upload-validation";
import type { DocumentLibraryFolder, Rotation, UploadResult } from "@/types/documents";

type Mode = "pdf" | "images";
type PendingImage = {
  id: string;
  file: File;
  previewUrl: string;
  rotation: Rotation;
};

const classificationLabels = {
  text: "Text-based PDF",
  scanned: "Scanned PDF",
  mixed: "Mixed PDF",
};

function normalizedPdfFilename(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "";
  return trimmed.toLowerCase().endsWith(".pdf") ? trimmed : `${trimmed}.pdf`;
}

function renamedPdfFile(file: File, name: string): File {
  return new File([file], name, {
    type: file.type || "application/pdf",
    lastModified: file.lastModified,
  });
}

type FolderModalStep = "choice" | "existing" | "new";

function suggestedFolderName(result: UploadResult): string {
  const filename =
    result.source_type === "pdf"
      ? result.original_filename
      : result.ordered_image_filenames[0] || "New upload";
  return filename.replace(/\.[^/.]+$/, "") || "New upload";
}

function nextRotation(current: Rotation, direction: "left" | "right"): Rotation {
  const amount = direction === "right" ? 90 : 270;
  return ((current + amount) % 360) as Rotation;
}

function SortablePage({
  page,
  pageNumber,
  totalPages,
  onMove,
  onRotate,
  onRemove,
}: {
  page: PendingImage;
  pageNumber: number;
  totalPages: number;
  onMove: (offset: -1 | 1) => void;
  onRotate: (direction: "left" | "right") => void;
  onRemove: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: page.id });

  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`rounded-2xl border bg-white p-3 shadow-sm ${isDragging ? "z-10 border-accent opacity-80" : "border-border"}`}
    >
      <div className="relative aspect-[4/5] overflow-hidden rounded-xl bg-[#eeece5]">
        <Image
          src={page.previewUrl}
          alt={`Preview of page ${pageNumber}: ${page.file.name}`}
          fill
          unoptimized
          className="object-contain transition-transform"
          style={{ transform: `rotate(${page.rotation}deg)` }}
        />
        <span className="absolute top-2 left-2 rounded-full bg-[#17202ae6] px-3 py-1 text-xs font-semibold text-white">
          Page {pageNumber}
        </span>
      </div>
      <p className="mt-3 truncate text-sm font-medium" title={page.file.name}>
        {page.file.name}
      </p>
      <p className="mt-1 text-xs text-muted">Rotation: {page.rotation}°</p>
      <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
        <button
          type="button"
          className="rounded-lg border border-border px-2 py-2 hover:bg-[#f4f1e9] disabled:opacity-40"
          onClick={() => onMove(-1)}
          disabled={pageNumber === 1}
        >
          Earlier
        </button>
        <button
          type="button"
          className="rounded-lg border border-border px-2 py-2 hover:bg-[#f4f1e9] disabled:opacity-40"
          onClick={() => onMove(1)}
          disabled={pageNumber === totalPages}
        >
          Later
        </button>
        <button
          type="button"
          className="rounded-lg border border-border px-2 py-2 hover:bg-[#f4f1e9]"
          onClick={() => onRotate("left")}
        >
          Rotate left
        </button>
        <button
          type="button"
          className="rounded-lg border border-border px-2 py-2 hover:bg-[#f4f1e9]"
          onClick={() => onRotate("right")}
        >
          Rotate right
        </button>
        <button
          type="button"
          className="cursor-grab rounded-lg border border-border px-2 py-2 hover:bg-[#f4f1e9] active:cursor-grabbing"
          aria-label={`Drag page ${pageNumber} to a new position`}
          {...attributes}
          {...listeners}
        >
          Drag to reorder
        </button>
        <button
          type="button"
          className="rounded-lg border border-[#d9b9b4] px-2 py-2 text-[#8a3e35] hover:bg-[#fff3f1]"
          onClick={onRemove}
        >
          Remove
        </button>
      </div>
    </li>
  );
}

function UploadDestinationModal({
  step,
  folders,
  currentDocumentId,
  loading,
  acting,
  error,
  newFolderName,
  onChooseExisting,
  onChooseNew,
  onBack,
  onSelectFolder,
  onNewFolderNameChange,
  onCreateFolder,
}: {
  step: FolderModalStep;
  folders: DocumentLibraryFolder[];
  currentDocumentId: string;
  loading: boolean;
  acting: boolean;
  error: string | null;
  newFolderName: string;
  onChooseExisting: () => void;
  onChooseNew: () => void;
  onBack: () => void;
  onSelectFolder: (folderId: string) => void;
  onNewFolderNameChange: (value: string) => void;
  onCreateFolder: () => void;
}) {
  const availableFolders = folders.filter((folder) => folder.id !== currentDocumentId);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-5">
      <div className="absolute inset-0 bg-[#17202a99]" aria-hidden="true" />
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="upload-destination-title"
        className="relative w-full max-w-lg rounded-2xl border border-border bg-surface p-6 shadow-[0_24px_70px_rgba(23,32,42,0.2)]"
      >
        {step === "choice" && (
          <>
            <p className="text-sm font-bold tracking-[0.12em] text-accent uppercase">
              Upload saved
            </p>
            <h2 id="upload-destination-title" className="mt-2 text-2xl font-semibold">
              Where should we save this upload?
            </h2>
            <p className="mt-2 text-muted">
              Choose a folder before you continue to the page text and listening steps.
            </p>
            <div className="mt-6 grid gap-3">
              <button
                type="button"
                onClick={onChooseExisting}
                className="min-h-14 rounded-xl border border-border bg-white px-4 text-left font-semibold hover:border-accent hover:bg-[#edf4f7]"
              >
                Save to existing folder
              </button>
              <button
                type="button"
                onClick={onChooseNew}
                className="min-h-14 rounded-xl border border-border bg-white px-4 text-left font-semibold hover:border-accent hover:bg-[#edf4f7]"
              >
                Create a new folder
              </button>
            </div>
          </>
        )}

        {step === "existing" && (
          <>
            <button
              type="button"
              onClick={onBack}
              className="font-semibold text-accent underline-offset-4 hover:underline"
            >
              ← Back
            </button>
            <h2 id="upload-destination-title" className="mt-4 text-2xl font-semibold">
              Choose a folder
            </h2>
            {loading ? (
              <p className="mt-4 text-muted">Loading your folders...</p>
            ) : availableFolders.length > 0 ? (
              <div className="mt-5 grid max-h-72 gap-2 overflow-y-auto">
                {availableFolders.map((folder) => (
                  <button
                    key={folder.id}
                    type="button"
                    disabled={acting}
                    onClick={() => onSelectFolder(folder.id)}
                    className="min-h-12 rounded-xl border border-border bg-white px-4 text-left font-semibold hover:border-accent hover:bg-[#edf4f7] disabled:opacity-60"
                  >
                    {folder.title}
                  </button>
                ))}
              </div>
            ) : (
              <p className="mt-4 text-muted">There are no other folders yet.</p>
            )}
          </>
        )}

        {step === "new" && (
          <>
            <h2 id="upload-destination-title" className="text-2xl font-semibold">
              Create a new folder
            </h2>
            <label className="mt-5 block">
              <span className="text-sm font-semibold text-muted">Folder name</span>
              <input
                autoFocus
                value={newFolderName}
                onChange={(event) => onNewFolderNameChange(event.target.value)}
                className="mt-2 min-h-12 w-full rounded-lg border border-border bg-white px-3"
              />
            </label>
            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                disabled={acting}
                onClick={onBack}
                className="min-h-11 rounded-lg border border-border px-4 font-semibold hover:bg-[#f8f6f0] disabled:opacity-60"
              >
                Back
              </button>
              <button
                type="button"
                disabled={acting || !newFolderName.trim()}
                onClick={onCreateFolder}
                className="min-h-11 rounded-lg bg-accent px-4 font-semibold text-white hover:bg-accent-dark disabled:opacity-60"
              >
                {acting ? "Creating..." : "Create and continue"}
              </button>
            </div>
          </>
        )}

        {error && (
          <p role="alert" className="mt-4 rounded-lg bg-[#fff3f1] p-3 text-sm text-[#783a33]">
            {error}
          </p>
        )}
      </section>
    </div>
  );
}

function UploadResultCard({
  result,
  libraryDocumentTitle,
  cardRef,
}: {
  result: UploadResult;
  libraryDocumentTitle?: string;
  cardRef: React.RefObject<HTMLElement | null>;
}) {
  return (
    <section
      ref={cardRef}
      className="mt-8 rounded-2xl border border-[#a9c5b3] bg-[#f4faf5] p-6"
      aria-live="polite"
    >
      <p className="text-sm font-bold tracking-wide text-[#376247] uppercase">
        Upload complete
      </p>
      <h2 className="mt-2 text-2xl font-semibold">
        {libraryDocumentTitle
          ? "Your new recording is prepared"
          : "Your document pages are prepared"}
      </h2>
      <dl className="mt-5 grid gap-4 sm:grid-cols-2">
        <div>
          <dt className="text-sm text-muted">Listening language</dt>
          <dd className="mt-1 font-semibold">
            {listeningLanguageLabel(result.target_language) ?? "Default voice"}
          </dd>
        </div>
        <div>
          <dt className="text-sm text-muted">Pages</dt>
          <dd className="mt-1 font-semibold">{result.total_pages}</dd>
        </div>
        <div>
          <dt className="text-sm text-muted">Status</dt>
          <dd className="mt-1 font-semibold">Uploaded</dd>
        </div>
        {result.source_type === "pdf" ? (
          <>
            <div>
              <dt className="text-sm text-muted">File</dt>
              <dd className="mt-1 break-all font-semibold">{result.original_filename}</dd>
            </div>
            <div>
              <dt className="text-sm text-muted">Page type</dt>
              <dd className="mt-1 font-semibold">
                {classificationLabels[result.classification]}
              </dd>
            </div>
          </>
        ) : (
          <div className="sm:col-span-2">
            <dt className="text-sm text-muted">Confirmed page order</dt>
            <dd className="mt-2">
              <ol className="list-inside list-decimal space-y-1">
                {result.ordered_image_filenames.map((filename, index) => (
                  <li className="break-all" key={`${filename}-${index}`}>
                    {filename}
                  </li>
                ))}
              </ol>
            </dd>
          </div>
        )}
      </dl>
      <div className="mt-6 border-t border-[#cbded1] pt-5">
        <h3 className="font-semibold">Prepared pages</h3>
        <ol className="mt-3 space-y-2">
          {result.pages.map((page) => (
            <li
              key={page.page_id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-white px-4 py-3 text-sm"
            >
              <span className="font-medium">
                Page {page.page_number}
                {page.original_filename ? ` · ${page.original_filename}` : ""}
              </span>
              <span className="text-muted">
                {page.extraction_method === "embedded_text"
                  ? "Page text saved"
                  : "Image ready for text reading"}
              </span>
            </li>
          ))}
        </ol>
      </div>
      <p className="mt-5 text-sm text-muted">
        Temporary document ID: {result.book_id}
      </p>
      <Link
        href={`/books/${result.book_id}`}
        className="mt-5 inline-flex min-h-12 items-center rounded-xl bg-accent px-6 py-3 font-semibold text-white shadow-sm transition hover:bg-accent-dark"
      >
        Review upload
      </Link>
    </section>
  );
}

export function DocumentUpload({
  initialLanguage,
  libraryDocumentId,
  libraryDocumentTitle,
}: {
  initialLanguage?: string;
  libraryDocumentId?: string;
  libraryDocumentTitle?: string;
}) {
  const [mode, setMode] = useState<Mode>("pdf");
  const [targetLanguage, setTargetLanguage] = useState<ListeningLanguage>(
    isListeningLanguage(initialLanguage) ? initialLanguage : defaultListeningLanguage,
  );
  const [pdf, setPdf] = useState<File | null>(null);
  const [pdfName, setPdfName] = useState("");
  const [pdfNameDraft, setPdfNameDraft] = useState("");
  const [editingPdfName, setEditingPdfName] = useState(false);
  const [images, setImages] = useState<PendingImage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [folderModalStep, setFolderModalStep] = useState<FolderModalStep | null>(null);
  const [folderModalFolders, setFolderModalFolders] = useState<DocumentLibraryFolder[]>([]);
  const [folderModalLoading, setFolderModalLoading] = useState(false);
  const [folderModalActing, setFolderModalActing] = useState(false);
  const [folderModalError, setFolderModalError] = useState<string | null>(null);
  const [newFolderName, setNewFolderName] = useState("");
  const previewUrls = useRef(new Set<string>());
  const imageInput = useRef<HTMLInputElement>(null);
  const resultCardRef = useRef<HTMLElement>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  useEffect(() => {
    const urls = previewUrls.current;
    return () => urls.forEach((url) => URL.revokeObjectURL(url));
  }, []);

  useEffect(() => {
    if (
      !result ||
      !resultCardRef.current ||
      typeof resultCardRef.current.scrollIntoView !== "function" ||
      typeof window === "undefined"
    ) {
      return;
    }

    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    resultCardRef.current.scrollIntoView({
      behavior: reduceMotion ? "auto" : "smooth",
      block: "start",
    });
  }, [result]);

  function openExistingFolders() {
    setFolderModalStep("existing");
    setFolderModalLoading(true);
    setFolderModalError(null);
    void getDocumentLibrary()
      .then((library) => setFolderModalFolders(library.folders))
      .catch((caught) => {
        setFolderModalError(
          caught instanceof Error ? caught.message : "Echo could not load your folders.",
        );
      })
      .finally(() => setFolderModalLoading(false));
  }

  function openNewFolder() {
    if (!result) return;
    setNewFolderName(suggestedFolderName(result));
    setFolderModalError(null);
    setFolderModalStep("new");
  }

  async function selectExistingFolder(folderId: string) {
    if (!result) return;
    setFolderModalActing(true);
    setFolderModalError(null);
    try {
      await assignDocumentToFolder(result.book_id, folderId);
      setFolderModalStep(null);
    } catch (caught) {
      setFolderModalError(
        caught instanceof Error
          ? caught.message
          : "Echo could not save this recording to the folder.",
      );
    } finally {
      setFolderModalActing(false);
    }
  }

  async function createNewFolder() {
    if (!result || !newFolderName.trim()) return;
    setFolderModalActing(true);
    setFolderModalError(null);
    try {
      await renameDocumentFolder(result.book_id, newFolderName.trim());
      setFolderModalStep(null);
    } catch (caught) {
      setFolderModalError(
        caught instanceof Error ? caught.message : "Echo could not create this folder.",
      );
    } finally {
      setFolderModalActing(false);
    }
  }

  function chooseMode(nextMode: Mode) {
    setMode(nextMode);
    setError(null);
    setResult(null);
  }

  function choosePdf(file: File | undefined) {
    if (!file) return;
    const message = validatePdf(file);
    if (message) {
      setError(message);
      return;
    }
    setPdf(file);
    setPdfName(file.name);
    setPdfNameDraft(file.name);
    setEditingPdfName(false);
    setError(null);
    setResult(null);
  }

  function savePdfName() {
    const nextName = normalizedPdfFilename(pdfNameDraft);
    if (!nextName) {
      setError("Please enter a PDF name.");
      return;
    }
    setPdfName(nextName);
    setPdfNameDraft(nextName);
    setEditingPdfName(false);
    setError(null);
    setResult(null);
  }

  function addImages(files: File[]) {
    const message = validateNewImages(files, images.length);
    if (message) {
      setError(message);
      return;
    }
    const additions = files.map((file) => {
      const previewUrl = URL.createObjectURL(file);
      previewUrls.current.add(previewUrl);
      return { id: crypto.randomUUID(), file, previewUrl, rotation: 0 as Rotation };
    });
    setImages((current) => [...current, ...additions]);
    setError(null);
    setResult(null);
    if (imageInput.current) imageInput.current.value = "";
  }

  function removeImage(id: string) {
    setImages((current) => {
      const removed = current.find((page) => page.id === id);
      if (removed) {
        URL.revokeObjectURL(removed.previewUrl);
        previewUrls.current.delete(removed.previewUrl);
      }
      return current.filter((page) => page.id !== id);
    });
    setResult(null);
  }

  function rotateImage(id: string, direction: "left" | "right") {
    setImages((current) =>
      current.map((page) =>
        page.id === id
          ? { ...page, rotation: nextRotation(page.rotation, direction) }
          : page,
      ),
    );
    setResult(null);
  }

  function moveImage(index: number, offset: -1 | 1) {
    setImages((current) => arrayMove(current, index, index + offset));
    setResult(null);
  }

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    setImages((current) => {
      const oldIndex = current.findIndex((page) => page.id === active.id);
      const newIndex = current.findIndex((page) => page.id === over.id);
      return arrayMove(current, oldIndex, newIndex);
    });
    setResult(null);
  }

  async function submit() {
    setError(null);
    setResult(null);
    if (mode === "pdf" && !pdf) {
      setError("Please choose a PDF first.");
      return;
    }
    const submittedPdfName = normalizedPdfFilename(pdfName);
    if (mode === "pdf" && !submittedPdfName) {
      setError("Please enter a PDF name.");
      return;
    }
    if (mode === "images" && images.length === 0) {
      setError("Please add at least one page image.");
      return;
    }

    setSubmitting(true);
    try {
      const uploadResult =
        mode === "pdf"
          ? await uploadPdf(renamedPdfFile(pdf as File, submittedPdfName), {
              libraryDocumentId,
              targetLanguage,
            })
          : await uploadImages(images, { libraryDocumentId, targetLanguage });
      setResult(uploadResult);
      if (!libraryDocumentId) {
        setNewFolderName(suggestedFolderName(uploadResult));
        setFolderModalError(null);
        setFolderModalStep("choice");
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The upload did not complete.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      {libraryDocumentTitle && (
        <div className="mb-6 rounded-2xl border border-[#b9d0da] bg-[#edf4f7] p-4">
          <p className="text-sm font-bold tracking-wide text-accent uppercase">
            Adding to library document
          </p>
          <p className="mt-1 text-lg font-semibold">{libraryDocumentTitle}</p>
        </div>
      )}

      <fieldset className="mb-6">
        <legend className="font-semibold">Listening language</legend>
        <div className="mt-3 grid gap-2 sm:grid-cols-3" aria-label="Listening language">
          {listeningLanguages.map((option) => (
            <button
              key={option.id}
              type="button"
              aria-pressed={targetLanguage === option.id}
              onClick={() => {
                setTargetLanguage(option.id);
                setResult(null);
              }}
              className={`min-h-12 rounded-xl border px-4 font-semibold transition ${
                targetLanguage === option.id
                  ? "border-accent bg-[#edf4f7] text-accent"
                  : "border-border bg-surface hover:border-accent"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </fieldset>

      <div
        className="grid gap-3 sm:grid-cols-2"
        role="group"
        aria-label="Document source"
      >
        <button
          type="button"
          aria-pressed={mode === "pdf"}
          onClick={() => chooseMode("pdf")}
          className={`min-h-24 rounded-2xl border p-5 text-left transition ${mode === "pdf" ? "border-accent bg-[#edf4f7] shadow-sm" : "border-border bg-surface hover:border-[#a7adb0]"}`}
        >
          <span className="block font-semibold">Upload PDF</span>
          <span className="mt-1 block text-sm text-muted">Choose one PDF document.</span>
        </button>
        <button
          type="button"
          aria-pressed={mode === "images"}
          onClick={() => chooseMode("images")}
          className={`min-h-24 rounded-2xl border p-5 text-left transition ${mode === "images" ? "border-accent bg-[#edf4f7] shadow-sm" : "border-border bg-surface hover:border-[#a7adb0]"}`}
        >
          <span className="block font-semibold">Upload Page Photos</span>
          <span className="mt-1 block text-sm text-muted">Choose JPG or PNG images.</span>
        </button>
      </div>

      {mode === "pdf" ? (
        <section className="mt-6 rounded-2xl border border-dashed border-[#aeb4b6] bg-surface p-7 text-center">
          <label className="inline-flex min-h-12 cursor-pointer items-center rounded-xl bg-accent px-6 py-3 font-semibold text-white hover:bg-accent-dark">
            Choose PDF
            <input
              className="sr-only"
              type="file"
              accept="application/pdf,.pdf"
              onChange={(event) => choosePdf(event.target.files?.[0])}
            />
          </label>
          <p className="mt-3 text-sm text-muted">Maximum size: 50 MB</p>
          {pdf && (
            <div className="mx-auto mt-6 max-w-xl rounded-xl border border-border bg-[#f8f6f0] p-4 text-left">
              {editingPdfName ? (
                <div className="mt-3">
                  <label
                    htmlFor="pdf-name"
                    className="text-sm font-semibold text-muted"
                  >
                    PDF name
                  </label>
                  <input
                    id="pdf-name"
                    value={pdfNameDraft}
                    onChange={(event) => {
                      setPdfNameDraft(event.target.value);
                      setResult(null);
                    }}
                    className="mt-2 min-h-11 w-full rounded-lg border border-border bg-white px-3"
                  />
                  <div className="mt-3 flex flex-wrap gap-3">
                    <button
                      type="button"
                      className="text-sm font-semibold text-accent underline underline-offset-4"
                      onClick={savePdfName}
                    >
                      Save name
                    </button>
                    <button
                      type="button"
                      className="text-sm font-semibold text-muted underline underline-offset-4"
                      onClick={() => {
                        setPdfNameDraft(pdfName);
                        setEditingPdfName(false);
                        setError(null);
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <p className="text-sm font-semibold text-muted">Upload name</p>
                  <p className="mt-1 break-all font-medium">{pdfName}</p>
                </>
              )}
              <p className="mt-1 text-sm text-muted">
                {(pdf.size / 1024 / 1024).toFixed(2)} MB
              </p>
              <div className="mt-3 flex flex-wrap gap-3">
                <button
                  type="button"
                  className="text-sm font-semibold text-accent underline underline-offset-4"
                  onClick={() => {
                    setPdfNameDraft(pdfName);
                    setEditingPdfName(true);
                    setError(null);
                  }}
                >
                  Rename
                </button>
                <button
                  type="button"
                  className="text-sm font-semibold text-[#8a3e35] underline underline-offset-4"
                  onClick={() => {
                    setPdf(null);
                    setPdfName("");
                    setPdfNameDraft("");
                    setEditingPdfName(false);
                    setResult(null);
                  }}
                >
                  Remove PDF
                </button>
              </div>
            </div>
          )}
        </section>
      ) : (
        <section className="mt-6">
          <div className="rounded-2xl border border-dashed border-[#aeb4b6] bg-surface p-6 text-center">
            <label className="inline-flex min-h-12 cursor-pointer items-center rounded-xl bg-accent px-6 py-3 font-semibold text-white hover:bg-accent-dark">
              {images.length ? "Add more photos" : "Choose page photos"}
              <input
                ref={imageInput}
                className="sr-only"
                type="file"
                accept="image/jpeg,image/png,.jpg,.jpeg,.png"
                multiple
                onChange={(event) => addImages(Array.from(event.target.files ?? []))}
              />
            </label>
            <p className="mt-3 text-sm text-muted">
              JPG or PNG, up to 15 MB each and 100 pages.
            </p>
          </div>
          {images.length > 0 && (
            <>
              <div className="mt-7 flex items-end justify-between gap-4">
                <div>
                  <h2 className="text-xl font-semibold">Arrange your pages</h2>
                  <p className="mt-1 text-sm text-muted">
                    Drag pages or use Earlier and Later. Page 1 will be read first.
                  </p>
                </div>
                <p className="shrink-0 text-sm font-semibold">{images.length} pages</p>
              </div>
              <DndContext
                sensors={sensors}
                collisionDetection={closestCenter}
                onDragEnd={handleDragEnd}
              >
                <SortableContext
                  items={images.map((page) => page.id)}
                  strategy={rectSortingStrategy}
                >
                  <ol className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    {images.map((page, index) => (
                      <SortablePage
                        key={page.id}
                        page={page}
                        pageNumber={index + 1}
                        totalPages={images.length}
                        onMove={(offset) => moveImage(index, offset)}
                        onRotate={(direction) => rotateImage(page.id, direction)}
                        onRemove={() => removeImage(page.id)}
                      />
                    ))}
                  </ol>
                </SortableContext>
              </DndContext>
            </>
          )}
        </section>
      )}

      {error && (
        <div
          role="alert"
          className="mt-6 rounded-xl border border-[#d9b9b4] bg-[#fff3f1] p-4 text-[#783a33]"
        >
          {error}
        </div>
      )}

      <button
        type="button"
        disabled={submitting}
        onClick={submit}
        className="mt-7 inline-flex min-h-14 w-full items-center justify-center gap-3 rounded-xl bg-accent px-7 py-3 font-semibold text-white shadow-sm transition hover:bg-accent-dark disabled:cursor-wait disabled:opacity-60 sm:w-auto"
      >
        {submitting && (
          <span
            aria-hidden="true"
            className="size-4 rounded-full border-2 border-white/40 border-t-white motion-safe:animate-spin"
          />
        )}
        {submitting ? "Preparing upload..." : "Prepare your upload"}
      </button>

      {result && (
        <UploadResultCard
          result={result}
          libraryDocumentTitle={libraryDocumentTitle}
          cardRef={resultCardRef}
        />
      )}

      {result && folderModalStep && (
        <UploadDestinationModal
          step={folderModalStep}
          folders={folderModalFolders}
          currentDocumentId={result.book_id}
          loading={folderModalLoading}
          acting={folderModalActing}
          error={folderModalError}
          newFolderName={newFolderName}
          onChooseExisting={openExistingFolders}
          onChooseNew={openNewFolder}
          onBack={() => {
            setFolderModalError(null);
            setFolderModalStep("choice");
          }}
          onSelectFolder={(folderId) => void selectExistingFolder(folderId)}
          onNewFolderNameChange={(value) => {
            setNewFolderName(value);
            setFolderModalError(null);
          }}
          onCreateFolder={() => void createNewFolder()}
        />
      )}
    </div>
  );
}
