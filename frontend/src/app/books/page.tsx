import { LibraryPageActions } from "@/components/auth/library-page-actions";
import { LibraryAuthGate } from "@/components/auth/library-auth-gate";

export default function DocumentsPage() {
  return (
    <main className="flex-1 px-5 py-8 sm:px-8 sm:py-12">
      <div className="mx-auto max-w-5xl">
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div>
            <p className="text-sm font-bold tracking-[0.14em] text-accent uppercase">
              Echo
            </p>
            <h1 className="mt-2 text-4xl font-semibold">Library</h1>
            <p className="mt-3 max-w-2xl leading-7 text-muted">
              Return to saved uploads, continue preparation, or resume listening.
            </p>
          </div>
          <LibraryPageActions />
        </div>
        <LibraryAuthGate />
      </div>
    </main>
  );
}
