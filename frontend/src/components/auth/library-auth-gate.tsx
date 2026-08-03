"use client";

import Link from "next/link";

import { useAuthSession } from "@/components/auth/use-auth-session";
import { DocumentLibrary } from "@/components/documents/document-library";

export function LibraryAuthGate() {
  const { isConfigured, isLoadingSession, isSignedIn } = useAuthSession();

  if (isLoadingSession) {
    return (
      <div className="mx-auto mt-10 max-w-2xl rounded-2xl border border-border bg-surface p-6 text-center shadow-[0_18px_55px_rgba(48,55,61,0.08)] transition-shadow duration-300 sm:p-8">
        <div
          aria-hidden="true"
          className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl border border-[#d6e1df] bg-[#edf4f2]"
        >
          <span className="h-3 w-3 rounded-full bg-accent" />
        </div>
        <p className="mt-5 text-lg font-semibold">Checking your account...</p>
        <p className="mx-auto mt-2 max-w-md leading-7 text-muted">
          Echo is confirming whether you are signed in before opening your library.
        </p>
      </div>
    );
  }

  if (!isConfigured) {
    return <DocumentLibrary />;
  }

  if (!isSignedIn) {
    return (
      <section className="mx-auto mt-10 max-w-2xl overflow-hidden rounded-2xl border border-border bg-surface shadow-[0_18px_55px_rgba(48,55,61,0.08)] transition-shadow duration-300 hover:shadow-[0_24px_70px_rgba(48,55,61,0.12)]">
        <div className="border-b border-border bg-[#fbfaf6] px-6 py-4 sm:px-8">
          <span className="inline-flex min-h-9 items-center rounded-full border border-[#d6e1df] bg-white px-3 text-sm font-semibold text-muted">
            Private library
          </span>
        </div>
        <div className="p-6 sm:p-8">
          <div
            aria-hidden="true"
            className="flex h-14 w-14 items-center justify-center rounded-2xl border border-[#cfdedb] bg-[#edf4f2]"
          >
            <span className="h-6 w-4 rounded-b-md rounded-t-sm border-2 border-accent border-t-4" />
          </div>
          <h2 className="mt-6 text-2xl font-semibold">
            Sign in to view your library
          </h2>
          <p className="mt-3 max-w-xl leading-7 text-muted">
            Echo needs an account before it can show saved uploads and listening
            progress.
          </p>
          <Link
            className="mt-6 inline-flex min-h-12 items-center justify-center rounded-xl bg-accent px-5 font-semibold text-white shadow-sm transition hover:bg-accent-dark hover:shadow-[0_10px_24px_rgba(48,101,134,0.22)]"
            href="/profile"
          >
            Sign in to view your library
          </Link>
          <p className="mt-4 text-sm leading-6 text-muted">
            You can return here after signing in.
          </p>
        </div>
      </section>
    );
  }

  return <DocumentLibrary />;
}
