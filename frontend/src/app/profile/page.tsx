import { AuthPanel } from "@/components/auth/auth-panel";

export default function ProfilePage() {
  return (
    <main className="flex-1 px-5 py-8 sm:px-8 sm:py-12">
      <div className="mx-auto max-w-5xl">
        <header>
          <p className="text-sm font-bold tracking-[0.14em] text-accent uppercase">
            Echo
          </p>
          <h1 className="mt-2 text-4xl font-semibold">Profile</h1>
          <p className="mt-3 max-w-2xl leading-7 text-muted">
            Connect Echo to Supabase Auth so later document saves and listening
            progress can belong to your account.
          </p>
        </header>

        <section className="mt-8 rounded-2xl border border-border bg-surface p-5 shadow-[0_14px_40px_rgba(48,55,61,0.05)] sm:p-6">
          <h2 className="text-2xl font-semibold">User information</h2>
          <dl className="mt-5 grid gap-4 sm:grid-cols-2">
            <div>
              <dt className="text-sm font-semibold text-muted">Account mode</dt>
              <dd className="mt-1 text-lg font-semibold">Supabase Auth</dd>
            </div>
            <div>
              <dt className="text-sm font-semibold text-muted">Library storage</dt>
              <dd className="mt-1 text-lg font-semibold">Local until Step 3</dd>
            </div>
          </dl>
        </section>

        <AuthPanel />
      </div>
    </main>
  );
}
