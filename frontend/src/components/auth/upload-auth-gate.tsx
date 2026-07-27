"use client";

import Link from "next/link";

import { useAuthSession } from "@/components/auth/use-auth-session";
import { DocumentUpload } from "@/components/upload/document-upload";

type UploadAuthGateProps = {
  initialLanguage?: string;
  libraryDocumentId?: string;
  libraryDocumentTitle?: string;
};

export function UploadAuthGate({
  initialLanguage,
  libraryDocumentId,
  libraryDocumentTitle,
}: UploadAuthGateProps) {
  const { isConfigured, isLoadingSession, isSignedIn } = useAuthSession();

  if (isLoadingSession) {
    return (
      <div className="rounded-2xl border border-border bg-surface p-5 shadow-[0_14px_40px_rgba(48,55,61,0.05)] sm:p-6">
        <p className="text-lg font-semibold">Checking your account...</p>
        <p className="mt-2 leading-7 text-muted">
          Echo is confirming whether you are signed in before upload starts.
        </p>
      </div>
    );
  }

  if (!isConfigured || !isSignedIn) {
    return (
      <div className="rounded-2xl border border-border bg-surface p-5 shadow-[0_14px_40px_rgba(48,55,61,0.05)] sm:p-6">
        <h2 className="text-2xl font-semibold">Sign in to upload files</h2>
        <p className="mt-2 max-w-2xl leading-7 text-muted">
          Echo needs an account before it can accept new PDFs or page photos.
        </p>
        <Link
          className="mt-5 inline-flex min-h-12 items-center justify-center rounded-xl bg-accent px-5 font-semibold text-white hover:bg-accent-dark"
          href="/profile"
        >
          Sign in to start uploading
        </Link>
      </div>
    );
  }

  return (
    <section className="mt-5 rounded-2xl border border-border bg-surface p-5 shadow-[0_14px_40px_rgba(48,55,61,0.05)] sm:p-6">
      <DocumentUpload
        initialLanguage={initialLanguage}
        libraryDocumentId={libraryDocumentId}
        libraryDocumentTitle={libraryDocumentTitle}
      />
    </section>
  );
}
