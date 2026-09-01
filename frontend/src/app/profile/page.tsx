import { AuthPanel } from "@/components/auth/auth-panel";

export default function ProfilePage() {
  return (
    <main className="flex-1 px-5 py-4 sm:px-8 sm:py-6">
      <div className="mx-auto max-w-5xl">
        <header>
          <p className="text-sm font-bold tracking-[0.14em] text-accent uppercase">
            Echo
          </p>
          <h1 className="mt-2 text-4xl font-semibold">Profile</h1>
          <p className="mt-3 max-w-2xl leading-7 text-muted">
            Manage your Echo account and saved document access.
          </p>
        </header>

        <AuthPanel />
      </div>
    </main>
  );
}
