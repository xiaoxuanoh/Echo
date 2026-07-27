"use client";

import type { Session } from "@supabase/supabase-js";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { getSupabaseBrowserClient } from "@/lib/supabase/browser";

type AuthMode = "sign-in" | "sign-up";

export function AuthPanel() {
  const supabase = useMemo(() => getSupabaseBrowserClient(), []);
  const [session, setSession] = useState<Session | null>(null);
  const [isLoadingSession, setIsLoadingSession] = useState(Boolean(supabase));
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [mode, setMode] = useState<AuthMode>("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!supabase) {
      return;
    }

    let isMounted = true;

    supabase.auth.getSession().then(({ data }) => {
      if (isMounted) {
        setSession(data.session);
        setIsLoadingSession(false);
      }
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
    });

    return () => {
      isMounted = false;
      subscription.unsubscribe();
    };
  }, [supabase]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!supabase) {
      return;
    }

    setIsSubmitting(true);
    setError(null);
    setMessage(null);

    const credentials = { email: email.trim(), password };
    const { data, error: authError } =
      mode === "sign-in"
        ? await supabase.auth.signInWithPassword(credentials)
        : await supabase.auth.signUp(credentials);

    setIsSubmitting(false);

    if (authError) {
      setError(authError.message);
      return;
    }

    setPassword("");
    setSession(data.session);
    setMessage(
      mode === "sign-up" && !data.session
        ? "Check your email to confirm your account."
        : "You are signed in.",
    );
  }

  async function handleSignOut() {
    if (!supabase) {
      return;
    }

    setIsSubmitting(true);
    setError(null);
    setMessage(null);

    const { error: signOutError } = await supabase.auth.signOut();

    setIsSubmitting(false);

    if (signOutError) {
      setError(signOutError.message);
      return;
    }

    setSession(null);
    setMessage("You are signed out.");
  }

  if (!supabase) {
    return (
      <section className="mt-8 rounded-2xl border border-border bg-surface p-5 shadow-[0_14px_40px_rgba(48,55,61,0.05)] sm:p-6">
        <h2 className="text-2xl font-semibold">Supabase Auth</h2>
        <p className="mt-3 leading-7 text-muted">
          Add `NEXT_PUBLIC_SUPABASE_URL` and
          `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` to `frontend/.env.local` to
          enable sign in.
        </p>
      </section>
    );
  }

  return (
    <section className="mt-8 rounded-2xl border border-border bg-surface p-5 shadow-[0_14px_40px_rgba(48,55,61,0.05)] sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold">Supabase Auth</h2>
          <p className="mt-2 leading-7 text-muted">
            Sign in before Echo starts saving documents and progress to your
            Supabase account.
          </p>
        </div>
        <span className="rounded-full border border-border px-3 py-1 text-sm font-semibold text-muted">
          {isLoadingSession ? "Checking session" : session ? "Signed in" : "Signed out"}
        </span>
      </div>

      {session ? (
        <div className="mt-6 grid gap-5 sm:grid-cols-[1fr_auto] sm:items-end">
          <dl className="grid gap-4 sm:grid-cols-2">
            <div>
              <dt className="text-sm font-semibold text-muted">Email</dt>
              <dd className="mt-1 break-all text-lg font-semibold">
                {session.user.email}
              </dd>
            </div>
            <div>
              <dt className="text-sm font-semibold text-muted">User ID</dt>
              <dd className="mt-1 break-all font-mono text-sm">{session.user.id}</dd>
            </div>
          </dl>
          <button
            className="inline-flex min-h-12 items-center justify-center rounded-xl border border-border bg-background px-5 font-semibold text-foreground hover:bg-[#f8f6f0] disabled:cursor-not-allowed disabled:opacity-60"
            disabled={isSubmitting}
            onClick={handleSignOut}
            type="button"
          >
            Sign out
          </button>
        </div>
      ) : (
        <form className="mt-6 grid gap-4" onSubmit={handleSubmit}>
          <div className="flex rounded-xl border border-border bg-background p-1">
            {(["sign-in", "sign-up"] as const).map((nextMode) => (
              <button
                className={[
                  "min-h-10 flex-1 rounded-lg px-4 text-sm font-semibold transition-colors",
                  mode === nextMode
                    ? "bg-accent text-white"
                    : "text-muted hover:text-foreground",
                ].join(" ")}
                key={nextMode}
                onClick={() => {
                  setMode(nextMode);
                  setError(null);
                  setMessage(null);
                }}
                type="button"
              >
                {nextMode === "sign-in" ? "Sign in" : "Create account"}
              </button>
            ))}
          </div>

          <label className="grid gap-2 font-semibold" htmlFor="auth-email">
            Email
            <input
              autoComplete="email"
              className="min-h-12 rounded-xl border border-border bg-background px-4 font-normal"
              id="auth-email"
              onChange={(event) => setEmail(event.target.value)}
              required
              type="email"
              value={email}
            />
          </label>

          <label className="grid gap-2 font-semibold" htmlFor="auth-password">
            Password
            <input
              autoComplete={mode === "sign-in" ? "current-password" : "new-password"}
              className="min-h-12 rounded-xl border border-border bg-background px-4 font-normal"
              id="auth-password"
              minLength={6}
              onChange={(event) => setPassword(event.target.value)}
              required
              type="password"
              value={password}
            />
          </label>

          <button
            className="inline-flex min-h-12 items-center justify-center rounded-xl bg-accent px-5 font-semibold text-white hover:bg-accent-dark disabled:cursor-not-allowed disabled:opacity-60"
            disabled={isSubmitting}
            type="submit"
          >
            {isSubmitting
              ? "Working..."
              : mode === "sign-in"
                ? "Sign in"
                : "Create account"}
          </button>
        </form>
      )}

      {message ? (
        <p className="mt-4 rounded-xl border border-[#b9d2c1] bg-[#ecf6ef] px-4 py-3 text-sm font-semibold text-[#28543a]">
          {message}
        </p>
      ) : null}
      {error ? (
        <p className="mt-4 rounded-xl border border-[#e3b6b6] bg-[#fff1f1] px-4 py-3 text-sm font-semibold text-[#8a3434]">
          {error}
        </p>
      ) : null}
    </section>
  );
}
