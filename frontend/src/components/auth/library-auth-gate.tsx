"use client";

import Link from "next/link";

import { useAuthSession } from "@/components/auth/use-auth-session";
import { DocumentLibrary } from "@/components/documents/document-library";

export function LibraryAuthGate() {
  const { isConfigured, isLoadingSession, isSignedIn } = useAuthSession();

  if (isLoadingSession) {
    return (
      <div className="mt-8 rounded-2xl border border-border bg-surface p-5 shadow-[0_14px_40px_rgba(48,55,61,0.05)] sm:p-6">
        <p className="text-lg font-semibold">Checking your account...</p>
        <p className="mt-2 leading-7 text-muted">
          Echo is confirming whether you are signed in before opening your
          library.
        </p>
      </div>
    );
  }

  if (!isConfigured || !isSignedIn) {
    return (
      <div className="mt-8 rounded-2xl border border-border bg-surface p-5 shadow-[0_14px_40px_rgba(48,55,61,0.05)] sm:p-6">
        <h2 className="text-2xl font-semibold">Sign in to view your library</h2>
        <p className="mt-2 max-w-2xl leading-7 text-muted">
          Echo needs an account before it can show saved uploads and listening
          progress.
        </p>
        <Link
          className="mt-5 inline-flex min-h-12 items-center justify-center rounded-xl bg-accent px-5 font-semibold text-white hover:bg-accent-dark"
          href="/profile"
        >
          Sign in to view your library
        </Link>
      </div>
    );
  }

  return <DocumentLibrary />;
}
