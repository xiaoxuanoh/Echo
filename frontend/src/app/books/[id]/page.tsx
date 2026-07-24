import Link from "next/link";

import { BookProcessing } from "@/components/books/book-processing";


export default async function BookPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <main className="flex-1 px-5 py-8 sm:px-8 sm:py-12">
      <div className="mx-auto max-w-5xl">
        <Link
          href="/books"
          className="inline-flex min-h-11 items-center font-semibold text-accent underline-offset-4 hover:underline"
        >
          ← Back to library
        </Link>
        <BookProcessing bookId={id} />
      </div>
    </main>
  );
}
