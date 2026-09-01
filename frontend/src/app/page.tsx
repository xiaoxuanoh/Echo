import { ListeningLanguageStart } from "@/components/language/listening-language-start";

const workflowSteps = [
  {
    label: "Document",
    title: "Upload pages",
    copy: "Add a PDF or page photos.",
    visual: "document",
  },
  {
    label: "Prepare",
    title: "Review the page order",
    copy: "Rotate, crop, and arrange pages.",
    visual: "prepare",
  },
  {
    label: "Generated audio",
    title: "Listen to generated audio",
    copy: "Echo reads the prepared pages.",
    visual: "audio",
  },
];

export default function Home() {
  return (
    <main className="flex flex-1 items-center px-6 py-12 sm:px-10 sm:py-14 lg:py-12">
      <div className="mx-auto grid w-full max-w-6xl gap-12 lg:grid-cols-[1fr_0.95fr] lg:items-center">
        <section>
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
          <ol className="grid gap-0">
            {workflowSteps.map((step, index) => (
              <li className="grid grid-cols-[4.5rem_1fr] gap-5" key={step.label}>
                <div className="flex flex-col items-center">
                  <div className="flex size-16 items-center justify-center rounded-2xl border border-[#d6e1df] bg-[#edf4f7]">
                    {step.visual === "document" ? (
                      <span
                        aria-hidden="true"
                        className="relative block h-9 w-7 rounded-sm border-2 border-accent bg-surface before:absolute before:top-2 before:left-1.5 before:h-0.5 before:w-4 before:rounded-full before:bg-[#7fa0bc] after:absolute after:top-4 after:left-1.5 after:h-0.5 after:w-3 before:content-[''] after:rounded-full after:bg-[#7fa0bc] after:content-['']"
                      />
                    ) : null}
                    {step.visual === "prepare" ? (
                      <span
                        aria-hidden="true"
                        className="grid h-9 w-9 grid-cols-3 grid-rows-3 gap-1"
                      >
                        {[...Array(9)].map((_, dotIndex) => (
                          <span
                            className={[
                              "rounded-full",
                              dotIndex === 4
                                ? "bg-accent"
                                : "bg-[#7fa0bc]",
                            ].join(" ")}
                            key={dotIndex}
                          />
                        ))}
                      </span>
                    ) : null}
                    {step.visual === "audio" ? (
                      <span
                        aria-hidden="true"
                        className="flex h-9 items-center gap-1"
                      >
                        {[18, 30, 24, 34, 20].map((height, barIndex) => (
                          <span
                            className="w-1.5 rounded-full bg-accent"
                            key={barIndex}
                            style={{ height }}
                          />
                        ))}
                      </span>
                    ) : null}
                  </div>
                  {index < workflowSteps.length - 1 ? (
                    <div className="h-10 w-px bg-border" aria-hidden="true" />
                  ) : null}
                </div>
                <div className={index < workflowSteps.length - 1 ? "pb-7" : ""}>
                  <p className="text-xs font-bold tracking-[0.14em] text-accent uppercase">
                    {step.label}
                  </p>
                  <h2 className="mt-1 font-semibold">{step.title}</h2>
                  <p className="mt-1 leading-6 text-muted">{step.copy}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </main>
  );
}
