"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import {
  defaultListeningLanguage,
  listeningLanguages,
  type ListeningLanguage,
} from "@/lib/listening-languages";

export function ListeningLanguageStart() {
  const [language, setLanguage] = useState<ListeningLanguage>(
    defaultListeningLanguage,
  );
  const uploadHref = useMemo(() => `/books/new?language=${language}`, [language]);

  return (
    <div className="mt-9">
      <fieldset>
        <legend className="text-base font-semibold">
          Hello. Choose how you&apos;d like to listen today.
        </legend>
        <div className="mt-3 grid max-w-xl gap-2 sm:grid-cols-3">
          {listeningLanguages.map((option) => (
            <button
              key={option.id}
              type="button"
              aria-pressed={language === option.id}
              onClick={() => setLanguage(option.id)}
              className={`min-h-12 rounded-xl border px-4 font-semibold transition ${
                language === option.id
                  ? "border-accent bg-[#edf4f7] text-accent"
                  : "border-border bg-surface hover:border-accent"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </fieldset>

      <div className="mt-7 flex flex-wrap gap-3">
        <Link
          href="/books"
          className="inline-flex min-h-14 items-center justify-center rounded-xl bg-accent px-7 py-3 text-base font-semibold text-white shadow-sm transition hover:bg-accent-dark"
        >
          Go to library
        </Link>
        <Link
          href={uploadHref}
          className="inline-flex min-h-14 items-center justify-center rounded-xl border border-border bg-surface px-7 py-3 text-base font-semibold text-foreground transition hover:bg-[#f8f6f0]"
        >
          Start uploading
        </Link>
      </div>
    </div>
  );
}
