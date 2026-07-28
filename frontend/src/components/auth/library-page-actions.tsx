"use client";

import Link from "next/link";

import { useAuthSession } from "@/components/auth/use-auth-session";

export function LibraryPageActions() {
  const { isSignedIn } = useAuthSession();

  if (!isSignedIn) {
    return null;
  }

  return (
    <div className="flex w-full flex-col gap-3 sm:w-auto">
      <Link
        href="/books/new"
        className="inline-flex min-h-12 items-center justify-center rounded-xl bg-accent px-5 font-semibold text-white shadow-sm transition hover:bg-accent-dark hover:shadow-[0_10px_24px_rgba(48,101,134,0.22)]"
      >
        Upload new file
      </Link>
      <Link
        href="/"
        className="inline-flex min-h-12 items-center justify-center rounded-xl border border-border bg-surface px-5 font-semibold text-foreground transition hover:bg-[#f8f6f0]"
      >
        Main page
      </Link>
    </div>
  );
}
