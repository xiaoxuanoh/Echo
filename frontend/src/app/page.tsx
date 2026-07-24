import { ListeningLanguageStart } from "@/components/language/listening-language-start";

export default function Home() {
  return (
    <main className="flex flex-1 items-center px-6 py-16 sm:px-10">
      <div className="mx-auto grid w-full max-w-6xl gap-12 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
        <section>
          <p className="mb-5 text-sm font-bold tracking-[0.18em] text-accent uppercase">
            Echo
          </p>
          <h1 className="max-w-3xl text-5xl leading-[1.08] font-semibold tracking-[-0.035em] sm:text-6xl">
            Turn your documents into spoken language.
          </h1>
          <p className="mt-7 max-w-2xl text-lg leading-8 text-muted">
            Upload a PDF or add photos of each page. Echo prepares them into
            clear audio you can listen to later.
          </p>
          <ListeningLanguageStart />
        </section>

        <section
          aria-label="How Echo works"
          className="rounded-3xl border border-border bg-surface p-7 shadow-[0_20px_60px_rgba(48,55,61,0.08)] sm:p-9"
        >
          <ol className="space-y-7">
            {[
              ["1", "Upload your document", "Choose one PDF or several page photos."],
              ["2", "Arrange your pages", "Check the order and rotate photos if needed."],
              ["3", "Ready for the next step", "Echo prepares a clean page-by-page result."],
            ].map(([number, title, copy]) => (
              <li className="flex gap-5" key={number}>
                <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-[#e4edf2] font-semibold text-accent">
                  {number}
                </span>
                <div>
                  <h2 className="font-semibold">{title}</h2>
                  <p className="mt-1 leading-6 text-muted">{copy}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </main>
  );
}
