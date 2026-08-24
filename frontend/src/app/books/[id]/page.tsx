import Link from "next/link";

import { DocumentProcessing } from "@/components/documents/document-processing";


export default async function DocumentPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <main className="flex-1 px-5 py-4 sm:px-8 sm:py-6">
      <div className="mx-auto max-w-5xl">
        <Link
          href="/books/new"
          className="inline-flex min-h-11 items-center font-semibold text-accent underline-offset-4 hover:underline"
        >
          ← Back to upload
        </Link>
        <DocumentProcessing documentId={id} />
      </div>
    </main>
  );
}
