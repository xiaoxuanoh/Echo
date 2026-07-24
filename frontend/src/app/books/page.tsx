import Link from "next/link";

import { BookLibrary } from "@/components/books/book-library";


export default function BooksPage() {
  return (
    <main className="flex-1 px-5 py-8 sm:px-8 sm:py-12">
      <div className="mx-auto max-w-5xl">
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div>
            <p className="text-sm font-bold tracking-[0.14em] text-accent uppercase">
              Library
            </p>
            <h1 className="mt-2 text-4xl font-semibold">Your Echo library</h1>
            <p className="mt-3 max-w-2xl leading-7 text-muted">
              Return to local documents, continue preparation, or resume listening.
            </p>
          </div>
          <div className="flex w-full flex-col gap-3 sm:w-auto">
            <Link
              href="/books/new"
              className="inline-flex min-h-12 items-center justify-center rounded-xl bg-accent px-5 font-semibold text-white hover:bg-accent-dark"
            >
              Start a new document
            </Link>
            <Link
              href="/"
              className="inline-flex min-h-12 items-center justify-center rounded-xl border border-border bg-surface px-5 font-semibold text-foreground hover:bg-[#f8f6f0]"
            >
              Main page
            </Link>
          </div>
        </div>
        <BookLibrary />
      </div>
    </main>
  );
}
