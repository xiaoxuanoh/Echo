"use client";

import type { Session } from "@supabase/supabase-js";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { getSupabaseBrowserClient } from "@/lib/supabase/browser";

type CreateAccountStep = "email" | "password" | "name";

function getDisplayName(session: Session) {
  const displayName = session.user.user_metadata?.display_name;

  return typeof displayName === "string" && displayName.trim()
    ? displayName.trim()
    : null;
}

export function AuthPanel() {
  const supabase = useMemo(() => getSupabaseBrowserClient(), []);
  const [session, setSession] = useState<Session | null>(null);
  const [isLoadingSession, setIsLoadingSession] = useState(Boolean(supabase));
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isCreateAccountOpen, setIsCreateAccountOpen] = useState(false);
  const [createAccountStep, setCreateAccountStep] =
    useState<CreateAccountStep>("email");
  const [createEmail, setCreateEmail] = useState("");
  const [createPassword, setCreatePassword] = useState("");
  const [createPasswordConfirmation, setCreatePasswordConfirmation] =
    useState("");
  const [createDisplayName, setCreateDisplayName] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);
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

  function openCreateAccount() {
    setCreateAccountStep("email");
    setCreateEmail(email);
    setCreatePassword("");
    setCreatePasswordConfirmation("");
    setCreateDisplayName("");
    setCreateError(null);
    setError(null);
    setMessage(null);
    setIsCreateAccountOpen(true);
  }

  function closeCreateAccount() {
    if (isSubmitting) {
      return;
    }

    setIsCreateAccountOpen(false);
    setCreateError(null);
  }

  async function handleSignIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!supabase) {
      return;
    }

    setIsSubmitting(true);
    setError(null);
    setMessage(null);

    const credentials = { email: email.trim(), password };
    const { data, error: authError } =
      await supabase.auth.signInWithPassword(credentials);

    setIsSubmitting(false);

    if (authError) {
      setError(authError.message);
      return;
    }

    setPassword("");
    setSession(data.session);
    setMessage("You are signed in.");
  }

  async function handleCreateAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!supabase) {
      return;
    }

    setCreateError(null);

    if (createAccountStep === "email") {
      setCreateEmail(createEmail.trim());
      setCreateAccountStep("password");
      return;
    }

    if (createAccountStep === "password") {
      if (createPassword !== createPasswordConfirmation) {
        setCreateError("Passwords do not match.");
        return;
      }

      setCreateAccountStep("name");
      return;
    }

    setIsSubmitting(true);
    setError(null);
    setMessage(null);

    const displayName = createDisplayName.trim();
    const { data, error: authError } = await supabase.auth.signUp({
      email: createEmail.trim(),
      password: createPassword,
      options: {
        data: {
          display_name: displayName,
        },
      },
    });

    setIsSubmitting(false);

    if (authError) {
      setCreateError(authError.message);
      return;
    }

    setIsCreateAccountOpen(false);
    setCreatePassword("");
    setCreatePasswordConfirmation("");
    setCreateDisplayName("");
    setSession(data.session);
    setMessage(
      data.session
        ? "Your account is ready."
        : "Check your email to confirm your account.",
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

  const displayName = session ? getDisplayName(session) : null;

  if (!supabase) {
    return (
      <section className="mt-8 rounded-2xl border border-border bg-surface p-5 shadow-[0_14px_40px_rgba(48,55,61,0.05)] sm:p-6">
        <h2 className="text-2xl font-semibold">Supabase Auth</h2>
        <p className="mt-3 max-w-2xl leading-7 text-muted">
          Sign in is not available until the local Supabase settings are added.
        </p>
        <p className="mt-3 rounded-xl border border-border bg-background px-4 py-3 text-sm text-muted">
          Add <code>NEXT_PUBLIC_SUPABASE_URL</code> and{" "}
          <code>NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY</code> to{" "}
          <code>frontend/.env.local</code>.
        </p>
      </section>
    );
  }

  return (
    <>
      <section className="mt-8 rounded-2xl border border-border bg-surface p-5 shadow-[0_14px_40px_rgba(48,55,61,0.05)] sm:p-6">
        {session ? (
          <>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h2 className="text-2xl font-semibold">User information</h2>
                {displayName ? (
                  <p className="mt-2 leading-7 text-muted">
                    Welcome, {displayName}.
                  </p>
                ) : null}
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <button
                  className="inline-flex min-h-12 items-center justify-center rounded-xl border border-[#d98080] bg-[#fff1f1] px-5 font-semibold text-[#8a3434] hover:bg-[#f8dede] disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={isSubmitting}
                  onClick={handleSignOut}
                  type="button"
                >
                  Sign out
                </button>
              </div>
            </div>

            <dl className="mt-5 grid gap-5 sm:grid-cols-2">
              <div>
                <dt className="text-sm font-semibold text-muted">Name</dt>
                <dd className="mt-1 break-all text-lg font-semibold">
                  {displayName ?? "Name not set yet"}
                </dd>
              </div>
              <div>
                <dt className="text-sm font-semibold text-muted">Email address</dt>
                <dd className="mt-1 break-all text-lg font-semibold">
                  {session.user.email}
                </dd>
              </div>
              <div>
                <dt className="text-sm font-semibold text-muted">Library sync</dt>
                <dd className="mt-1 text-lg font-semibold">Ready for cloud sync</dd>
                <dd className="mt-1 leading-7 text-muted">
                  Cloud sync will start in the next persistence step.
                </dd>
              </div>
            </dl>

            <details className="mt-5 rounded-xl border border-border bg-background px-4 py-3 text-sm text-muted">
              <summary className="cursor-pointer font-semibold text-foreground">
                Technical details
              </summary>
              <dl className="mt-3 grid gap-3 sm:grid-cols-2">
                <div>
                  <dt className="font-semibold">Account provider</dt>
                  <dd className="mt-1">Supabase Auth</dd>
                </div>
                <div>
                  <dt className="font-semibold">User ID</dt>
                  <dd className="mt-1 break-all font-mono">{session.user.id}</dd>
                </div>
              </dl>
            </details>
          </>
        ) : (
          <>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h2 className="text-2xl font-semibold">Sign in</h2>
                <p className="mt-2 leading-7 text-muted">
                  Sign in now so Echo can connect your documents and progress to
                  your account when cloud sync is enabled.
                </p>
              </div>
              <span className="rounded-full border border-border px-3 py-1 text-sm font-semibold text-muted">
                {isLoadingSession ? "Checking session" : "Signed out"}
              </span>
            </div>

            <form className="mt-6 grid gap-4" onSubmit={handleSignIn}>
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
                  autoComplete="current-password"
                  className="min-h-12 rounded-xl border border-border bg-background px-4 font-normal"
                  id="auth-password"
                  minLength={6}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  type="password"
                  value={password}
                />
              </label>

              <div className="flex flex-wrap gap-3">
                <button
                  className="inline-flex min-h-12 items-center justify-center rounded-xl bg-accent px-5 font-semibold text-white hover:bg-accent-dark disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={isSubmitting}
                  type="submit"
                >
                  {isSubmitting ? "Working..." : "Sign in"}
                </button>
                <button
                  className="inline-flex min-h-12 items-center justify-center rounded-xl border border-border bg-background px-5 font-semibold text-foreground hover:bg-[#f8f6f0] disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={isSubmitting}
                  onClick={openCreateAccount}
                  type="button"
                >
                  Create account
                </button>
              </div>
            </form>
          </>
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

      {isCreateAccountOpen ? (
        <div
          aria-labelledby="create-account-title"
          aria-modal="true"
          className="fixed inset-0 z-50 grid place-items-center bg-[rgba(48,55,61,0.35)] px-5 py-8"
          role="dialog"
        >
          <form
            className="w-full max-w-md rounded-2xl border border-border bg-surface p-5 shadow-[0_18px_60px_rgba(48,55,61,0.2)] sm:p-6"
            onSubmit={handleCreateAccount}
          >
            <div>
              <p className="text-sm font-bold tracking-[0.14em] text-accent uppercase">
                Create account
              </p>
              <h2 className="mt-2 text-2xl font-semibold" id="create-account-title">
                {createAccountStep === "email"
                  ? "What is your email?"
                  : createAccountStep === "password"
                    ? "Create a password"
                    : "What should Echo call you?"}
              </h2>
              <p className="mt-2 leading-7 text-muted">
                {createAccountStep === "email"
                  ? "Use the email you want for your Echo account."
                  : createAccountStep === "password"
                    ? "Confirm it once so you do not get locked out by a typo."
                    : "This name is only used for friendly messages in Echo."}
              </p>
            </div>

            {createAccountStep === "email" ? (
              <label
                className="mt-5 grid gap-2 font-semibold"
                htmlFor="create-account-email"
              >
                Email
                <input
                  autoComplete="email"
                  className="min-h-12 rounded-xl border border-border bg-background px-4 font-normal"
                  id="create-account-email"
                  onChange={(event) => setCreateEmail(event.target.value)}
                  required
                  type="email"
                  value={createEmail}
                />
              </label>
            ) : null}

            {createAccountStep === "password" ? (
              <div className="mt-5 grid gap-4">
                <label className="grid gap-2 font-semibold" htmlFor="create-account-password">
                  Password
                  <input
                    autoComplete="new-password"
                    className="min-h-12 rounded-xl border border-border bg-background px-4 font-normal"
                    id="create-account-password"
                    minLength={6}
                    onChange={(event) => setCreatePassword(event.target.value)}
                    required
                    type="password"
                    value={createPassword}
                  />
                </label>
                <label
                  className="grid gap-2 font-semibold"
                  htmlFor="create-account-password-confirmation"
                >
                  Confirm password
                  <input
                    autoComplete="new-password"
                    className="min-h-12 rounded-xl border border-border bg-background px-4 font-normal"
                    id="create-account-password-confirmation"
                    minLength={6}
                    onChange={(event) =>
                      setCreatePasswordConfirmation(event.target.value)
                    }
                    required
                    type="password"
                    value={createPasswordConfirmation}
                  />
                </label>
              </div>
            ) : null}

            {createAccountStep === "name" ? (
              <label
                className="mt-5 grid gap-2 font-semibold"
                htmlFor="create-account-name"
              >
                Name
                <input
                  autoComplete="name"
                  className="min-h-12 rounded-xl border border-border bg-background px-4 font-normal"
                  id="create-account-name"
                  maxLength={80}
                  onChange={(event) => setCreateDisplayName(event.target.value)}
                  required
                  type="text"
                  value={createDisplayName}
                />
              </label>
            ) : null}

            {createError ? (
              <p className="mt-4 rounded-xl border border-[#e3b6b6] bg-[#fff1f1] px-4 py-3 text-sm font-semibold text-[#8a3434]">
                {createError}
              </p>
            ) : null}

            <div className="mt-6 flex flex-wrap justify-end gap-3">
              <button
                className="inline-flex min-h-11 items-center justify-center rounded-xl border border-border bg-background px-5 font-semibold text-foreground hover:bg-[#f8f6f0] disabled:cursor-not-allowed disabled:opacity-60"
                disabled={isSubmitting}
                onClick={closeCreateAccount}
                type="button"
              >
                Cancel
              </button>
              <button
                className="inline-flex min-h-11 items-center justify-center rounded-xl bg-accent px-5 font-semibold text-white hover:bg-accent-dark disabled:cursor-not-allowed disabled:opacity-60"
                disabled={isSubmitting}
                type="submit"
              >
                {isSubmitting
                  ? "Working..."
                  : createAccountStep === "name"
                    ? "Create account"
                    : "Continue"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </>
  );
}
