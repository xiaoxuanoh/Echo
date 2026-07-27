import Link from "next/link";

import { DocumentUpload } from "@/components/upload/document-upload";

export default async function NewDocumentPage({
  searchParams,
}: {
  searchParams: Promise<{ folderId?: string; folderTitle?: string; language?: string }>;
}) {
  const { folderId, folderTitle, language } = await searchParams;
  const isAddingRecording = Boolean(folderId);

  return (
    <main className="flex-1 px-5 py-8 sm:px-8 sm:py-12">
      <div className="mx-auto max-w-5xl">
        <Link
          href={isAddingRecording ? "/books" : "/"}
          className="inline-flex min-h-11 items-center font-semibold text-accent underline-offset-4 hover:underline"
        >
          {isAddingRecording ? "← Back to library" : "← Echo home"}
        </Link>
        <header className="mt-8 rounded-2xl border border-border bg-surface p-5 shadow-[0_14px_40px_rgba(48,55,61,0.05)] sm:p-6">
          <p className="text-sm font-bold tracking-[0.16em] text-accent uppercase">
            {isAddingRecording ? "New recording" : "New upload"}
          </p>
          <h1 className="mt-2 text-3xl font-semibold sm:text-4xl">
            {isAddingRecording ? "Upload more pages" : "Start uploading"}
          </h1>
          <p className="mt-2 max-w-3xl leading-7 text-muted">
            {isAddingRecording
              ? "Choose another PDF or more page photos. Echo will save this as a separate recording inside the selected document."
              : "Choose a PDF or add photographs of each page. You can check their order before Echo prepares them."}
          </p>
        </header>
        <section className="mt-5 rounded-2xl border border-border bg-surface p-5 shadow-[0_14px_40px_rgba(48,55,61,0.05)] sm:p-6">
          <DocumentUpload
            initialLanguage={language}
            libraryDocumentId={folderId}
            libraryDocumentTitle={folderTitle}
          />
        </section>
      </div>
    </main>
  );
}
