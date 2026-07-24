import Link from "next/link";

import { BookUpload } from "@/components/upload/book-upload";

export default async function NewBookPage({
  searchParams,
}: {
  searchParams: Promise<{ folderId?: string; folderTitle?: string; language?: string }>;
}) {
  const { folderId, folderTitle, language } = await searchParams;
  const isAddingRecording = Boolean(folderId);

  return (
    <main className="flex-1 px-5 py-8 sm:px-8 sm:py-12">
      <div className="mx-auto max-w-6xl">
        <Link
          href={isAddingRecording ? "/books" : "/"}
          className="inline-flex min-h-11 items-center font-semibold text-accent underline-offset-4 hover:underline"
        >
          {isAddingRecording ? "← Back to library" : "← Echo home"}
        </Link>
        <header className="mt-7 max-w-3xl">
          <p className="text-sm font-bold tracking-[0.16em] text-accent uppercase">
            {isAddingRecording ? "New recording" : "New document"}
          </p>
          <h1 className="mt-3 text-4xl font-semibold tracking-[-0.025em] sm:text-5xl">
            {isAddingRecording ? "Upload more pages" : "Start uploading"}
          </h1>
          <p className="mt-4 text-lg leading-8 text-muted">
            {isAddingRecording
              ? "Choose another PDF or more page photos. Echo will save this as a separate recording inside the selected document."
              : "Choose a PDF or add photographs of each page. You can check their order before Echo prepares them."}
          </p>
        </header>
        <section className="mt-10 rounded-3xl border border-border bg-surface p-5 shadow-[0_20px_60px_rgba(48,55,61,0.06)] sm:p-8">
          <BookUpload
            initialLanguage={language}
            libraryBookId={folderId}
            libraryBookTitle={folderTitle}
          />
        </section>
      </div>
    </main>
  );
}
