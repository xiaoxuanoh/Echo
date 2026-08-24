import Link from "next/link";

import { DocumentAudioPlayer } from "@/components/documents/document-audio-player";


export default async function ListenPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <main className="flex-1 px-5 py-4 sm:px-8 sm:py-6">
      <div className="mx-auto max-w-5xl">
        <div className="flex flex-wrap gap-4">
          <Link
            href="/books"
            className="inline-flex min-h-11 items-center font-semibold text-accent underline-offset-4 hover:underline"
          >
            ← Back to library
          </Link>
          <Link
            href={`/books/${id}`}
            className="inline-flex min-h-11 items-center font-semibold text-accent underline-offset-4 hover:underline"
          >
            Raw text
          </Link>
        </div>
        <DocumentAudioPlayer documentId={id} />
      </div>
    </main>
  );
}
