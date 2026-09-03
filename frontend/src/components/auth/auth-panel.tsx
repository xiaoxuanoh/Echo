"use client";

import type { Session } from "@supabase/supabase-js";
import { FormEvent, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { useAuthSession } from "@/components/auth/use-auth-session";
import { profileHrefForNext, safeNextPath } from "@/lib/auth-redirect";

type CreateAccountStep = "email" | "password" | "name";
type SignInStep = "email" | "password";

function getDisplayName(session: Session) {
  const displayName = session.user.user_metadata?.display_name;

  return typeof displayName === "string" && displayName.trim()
    ? displayName.trim()
    : null;
}

export function AuthPanel() {
  const { authEvent, isLoadingSession, session, setSession, supabase } =
    useAuthSession();
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextPath = safeNextPath(searchParams.get("next"));
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [signInStep, setSignInStep] = useState<SignInStep>("email");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [resetPassword, setResetPassword] = useState("");
  const [resetPasswordConfirmation, setResetPasswordConfirmation] = useState("");
  const [passwordRecoveryComplete, setPasswordRecoveryComplete] = useState(false);
  const [isCreateAccountOpen, setIsCreateAccountOpen] = useState(false);
  const [createAccountStep, setCreateAccountStep] =
    useState<CreateAccountStep>("email");
  const [createEmail, setCreateEmail] = useState("");
  const [createPassword, setCreatePassword] = useState("");
  const [createPasswordConfirmation, setCreatePasswordConfirmation] =
    useState("");
  const [createDisplayName, setCreateDisplayName] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);
  const [confirmationEmail, setConfirmationEmail] = useState<string | null>(null);
  const [passwordResetEmail, setPasswordResetEmail] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function openCreateAccount() {
    setCreateAccountStep("email");
    setCreateEmail(email);
    setCreatePassword("");
    setCreatePasswordConfirmation("");
    setCreateDisplayName("");
    setCreateError(null);
    setConfirmationEmail(null);
    setPasswordResetEmail(null);
    setError(null);
    setMessage(null);
    setIsCreateAccountOpen(true);
  }

  function returnToEmailStep() {
    if (isSubmitting) {
      return;
    }

    setPassword("");
    setError(null);
    setMessage(null);
    setConfirmationEmail(null);
    setPasswordResetEmail(null);
    setSignInStep("email");
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

    setError(null);
    setMessage(null);
    setConfirmationEmail(null);
    setPasswordResetEmail(null);

    if (signInStep === "email") {
      setEmail(email.trim());
      setSignInStep("password");
      return;
    }

    setIsSubmitting(true);

    const credentials = { email: email.trim(), password };
    const { data, error: authError } =
      await supabase.auth.signInWithPassword(credentials);

    setIsSubmitting(false);

    if (authError) {
      setError(authError.message);
      return;
    }

    setPassword("");
    setSignInStep("email");
    setSession(data.session);
    if (data.session && nextPath) {
      router.replace(nextPath);
      return;
    }
    setMessage("You are signed in.");
  }

  async function handleSendPasswordReset() {
    if (!supabase || !email.trim()) {
      return;
    }

    setIsSubmitting(true);
    setError(null);
    setMessage(null);
    setConfirmationEmail(null);
    setPasswordResetEmail(null);

    const { error: resetError } = await supabase.auth.resetPasswordForEmail(
      email.trim(),
      {
        redirectTo: `${window.location.origin}/profile`,
      },
    );

    setIsSubmitting(false);

    if (resetError) {
      setError(resetError.message);
      return;
    }

    setPasswordResetEmail(email.trim());
  }

  async function handleUpdateRecoveredPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!supabase) {
      return;
    }

    setError(null);
    setMessage(null);

    if (resetPassword !== resetPasswordConfirmation) {
      setError("Passwords do not match.");
      return;
    }

    setIsSubmitting(true);

    const { error: updateError } = await supabase.auth.updateUser({
      password: resetPassword,
    });

    setIsSubmitting(false);

    if (updateError) {
      setError(updateError.message);
      return;
    }

    setResetPassword("");
    setResetPasswordConfirmation("");
    setPasswordRecoveryComplete(true);
    setMessage("Your password has been updated.");
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
    setPasswordResetEmail(null);

    const displayName = createDisplayName.trim();
    const emailRedirectTo =
      nextPath && typeof window !== "undefined"
        ? `${window.location.origin}${profileHrefForNext(nextPath)}`
        : undefined;
    const signUpOptions = {
      data: {
        display_name: displayName,
      },
      ...(emailRedirectTo ? { emailRedirectTo } : {}),
    };
    const { data, error: authError } = await supabase.auth.signUp({
      email: createEmail.trim(),
      password: createPassword,
      options: signUpOptions,
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

    if (data.session) {
      if (nextPath) {
        router.replace(nextPath);
        return;
      }
      setMessage("Your account is ready.");
      return;
    }

    setEmail(createEmail.trim());
    setPassword("");
    setSignInStep("email");
    setConfirmationEmail(createEmail.trim());
  }

  async function handleSignOut() {
    if (!supabase) {
      return;
    }

    setIsSubmitting(true);
    setError(null);
    setMessage(null);
    setConfirmationEmail(null);
    setPasswordResetEmail(null);

    const { error: signOutError } = await supabase.auth.signOut();

    setIsSubmitting(false);

    if (signOutError) {
      setError(signOutError.message);
      return;
    }

    setSession(null);
    setSignInStep("email");
    setPassword("");
    setMessage("You are signed out.");
  }

  const displayName = session ? getDisplayName(session) : null;
  const isPasswordRecovery =
    authEvent === "PASSWORD_RECOVERY" && !passwordRecoveryComplete;
  const shouldRedirectExistingSession =
    Boolean(session && nextPath) && authEvent !== "PASSWORD_RECOVERY";

  useEffect(() => {
    if (!shouldRedirectExistingSession || !nextPath) {
      return;
    }

    router.replace(nextPath);
  }, [nextPath, router, shouldRedirectExistingSession]);

  if (!supabase) {
    return (
      <section className="mx-auto mt-10 max-w-2xl overflow-hidden rounded-2xl border border-border bg-surface shadow-[0_18px_55px_rgba(48,55,61,0.08)] transition-shadow duration-300 hover:shadow-[0_24px_70px_rgba(48,55,61,0.12)]">
        <div className="border-b border-border bg-[#fbfaf6] px-6 py-4 sm:px-8">
          <span className="inline-flex min-h-9 items-center rounded-full border border-[#d6e1df] bg-white px-3 text-sm font-semibold text-muted">
            Account setup
          </span>
        </div>
        <div className="p-6 sm:p-8">
          <h2 className="text-2xl font-semibold">Supabase Auth</h2>
          <p className="mt-3 max-w-xl leading-7 text-muted">
            Sign in is not available until the local Supabase settings are added.
          </p>
          <p className="mt-5 rounded-xl border border-border bg-background px-4 py-3 text-sm text-muted">
            Add <code>NEXT_PUBLIC_SUPABASE_URL</code> and{" "}
            <code>NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY</code> to{" "}
            <code>frontend/.env.local</code>.
          </p>
        </div>
      </section>
    );
  }

  return (
    <>
      <section className="mx-auto mt-10 max-w-2xl overflow-hidden rounded-2xl border border-border bg-surface shadow-[0_18px_55px_rgba(48,55,61,0.08)] transition-shadow duration-300 hover:shadow-[0_24px_70px_rgba(48,55,61,0.12)]">
        {session && isPasswordRecovery ? (
          <div className="p-6 sm:p-8">
            <div>
              <div
                aria-hidden="true"
                className="flex h-14 w-14 items-center justify-center rounded-2xl border border-[#cfdedb] bg-[#edf4f2]"
              >
                <span className="h-6 w-4 rounded-b-md rounded-t-sm border-2 border-accent border-t-4" />
              </div>
              <h2 className="mt-6 text-2xl font-semibold">Choose a new password</h2>
              <p className="mt-3 max-w-xl leading-7 text-muted">
                Enter a new password for your Echo account.
              </p>
            </div>

            <form
              className="mt-6 grid gap-4"
              onSubmit={handleUpdateRecoveredPassword}
            >
              <label className="grid gap-2 font-semibold" htmlFor="reset-password">
                New password
                <input
                  autoComplete="new-password"
                  autoFocus
                  className="min-h-12 rounded-xl border border-border bg-background px-4 font-normal transition-colors duration-150 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-background"
                  id="reset-password"
                  minLength={6}
                  onChange={(event) => setResetPassword(event.target.value)}
                  required
                  type="password"
                  value={resetPassword}
                />
              </label>
              <label
                className="grid gap-2 font-semibold"
                htmlFor="reset-password-confirmation"
              >
                Confirm new password
                <input
                  autoComplete="new-password"
                  className="min-h-12 rounded-xl border border-border bg-background px-4 font-normal transition-colors duration-150 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-background"
                  id="reset-password-confirmation"
                  minLength={6}
                  onChange={(event) =>
                    setResetPasswordConfirmation(event.target.value)
                  }
                  required
                  type="password"
                  value={resetPasswordConfirmation}
                />
              </label>
              <button
                className="inline-flex min-h-12 items-center justify-center rounded-xl bg-accent px-5 font-semibold text-white shadow-sm transition-colors duration-150 hover:bg-accent-dark disabled:cursor-not-allowed disabled:opacity-60 sm:w-fit"
                disabled={isSubmitting}
                type="submit"
              >
                {isSubmitting ? "Working..." : "Update password"}
              </button>
            </form>
          </div>
        ) : session ? (
          <div className="p-6 sm:p-8">
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
                  className="inline-flex min-h-12 items-center justify-center rounded-xl border border-[#d98080] bg-[#fff1f1] px-5 font-semibold text-[#8a3434] transition hover:bg-[#f8dede] disabled:cursor-not-allowed disabled:opacity-60"
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
                <dt className="text-sm font-semibold text-muted">Library access</dt>
                <dd className="mt-1 text-lg font-semibold">
                  Ready for saved documents
                </dd>
                <dd className="mt-1 leading-7 text-muted">
                  Use your account to open your library and continue document work.
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
          </div>
        ) : (
          <>
            <div className="border-b border-border bg-[#fbfaf6] px-6 py-4 sm:px-8">
              <span className="inline-flex min-h-9 items-center rounded-full border border-[#d6e1df] bg-white px-3 text-sm font-semibold text-muted">
                {isLoadingSession ? "Checking session" : "Signed out"}
              </span>
            </div>
            <div className="p-6 sm:p-8">
              <div>
                <div
                  aria-hidden="true"
                  className="flex h-14 w-14 items-center justify-center rounded-2xl border border-[#cfdedb] bg-[#edf4f2]"
                >
                  <span className="h-6 w-4 rounded-b-md rounded-t-sm border-2 border-accent border-t-4" />
                </div>
                <h2 className="mt-6 text-2xl font-semibold">Sign in</h2>
                <p className="mt-3 max-w-xl leading-7 text-muted">
                  Sign in so Echo can keep your documents and listening progress
                  connected to your account.
                </p>
              </div>

              <form className="mt-6 grid gap-4" onSubmit={handleSignIn}>
                <div className="auth-step-panel grid gap-4" key={signInStep}>
                  {signInStep === "email" ? (
                    <label
                      className="grid gap-2 font-semibold"
                      htmlFor="auth-email"
                    >
                      Email
                      <input
                        autoComplete="email"
                        autoFocus
                        className="min-h-12 rounded-xl border border-border bg-background px-4 font-normal transition-colors duration-150 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-background"
                        id="auth-email"
                        onChange={(event) => setEmail(event.target.value)}
                        required
                        type="email"
                        value={email}
                      />
                    </label>
                  ) : (
                    <>
                      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-background px-4 py-3">
                        <span className="break-all text-sm font-semibold text-muted">
                          {email}
                        </span>
                        <button
                          className="font-semibold text-accent transition-colors duration-150 hover:text-accent-dark disabled:cursor-not-allowed disabled:opacity-60"
                          disabled={isSubmitting}
                          onClick={returnToEmailStep}
                          type="button"
                        >
                          Change
                        </button>
                      </div>
                      <label
                        className="grid gap-2 font-semibold"
                        htmlFor="auth-password"
                      >
                        Password
                        <input
                          autoComplete="current-password"
                          autoFocus
                          className="min-h-12 rounded-xl border border-border bg-background px-4 font-normal transition-colors duration-150 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-background"
                          id="auth-password"
                          minLength={6}
                          onChange={(event) => setPassword(event.target.value)}
                          required
                          type="password"
                          value={password}
                        />
                      </label>
                      <button
                        className="w-fit font-semibold text-accent transition-colors duration-150 hover:text-accent-dark disabled:cursor-not-allowed disabled:opacity-60"
                        disabled={isSubmitting}
                        onClick={handleSendPasswordReset}
                        type="button"
                      >
                        Forgot password?
                      </button>
                    </>
                  )}
                </div>

                <div className="flex flex-wrap justify-center gap-3">
                  <button
                    className="inline-flex min-h-12 items-center justify-center rounded-xl bg-accent px-5 font-semibold text-white shadow-sm transition-colors duration-150 hover:bg-accent-dark disabled:cursor-not-allowed disabled:opacity-60"
                    disabled={isSubmitting}
                    type="submit"
                  >
                    {isSubmitting
                      ? "Working..."
                      : signInStep === "email"
                        ? "Continue"
                        : "Sign in"}
                  </button>
                  <button
                    className="inline-flex min-h-12 items-center justify-center rounded-xl border border-border bg-background px-5 font-semibold text-foreground transition-colors duration-150 hover:bg-[#f8f6f0] disabled:cursor-not-allowed disabled:opacity-60"
                    disabled={isSubmitting}
                    onClick={openCreateAccount}
                    type="button"
                  >
                    Create account
                  </button>
                </div>
                <p className="text-center text-sm leading-6 text-muted">
                  Your library will be available after signing in.
                </p>
              </form>
            </div>
          </>
        )}

        {message ? (
          <p className="mx-6 mb-6 rounded-xl border border-[#b9d2c1] bg-[#ecf6ef] px-4 py-3 text-sm font-semibold text-[#28543a] sm:mx-8">
            {message}
          </p>
        ) : null}
        {confirmationEmail ? (
          <p className="mx-6 mb-6 rounded-xl border border-[#b9d0da] bg-[#edf4f7] px-4 py-3 text-sm font-semibold text-[#28516a] sm:mx-8">
            We sent a confirmation link to{" "}
            <strong className="break-all">{confirmationEmail}</strong>. Confirm
            your email, then return here to sign in.
          </p>
        ) : null}
        {passwordResetEmail ? (
          <p className="mx-6 mb-6 rounded-xl border border-[#b9d0da] bg-[#edf4f7] px-4 py-3 text-sm font-semibold text-[#28516a] sm:mx-8">
            We sent a password reset link to{" "}
            <strong className="break-all">{passwordResetEmail}</strong>. Follow
            the link in that email to choose a new password.
          </p>
        ) : null}
        {error ? (
          <p className="mx-6 mb-6 rounded-xl border border-[#e3b6b6] bg-[#fff1f1] px-4 py-3 text-sm font-semibold text-[#8a3434] sm:mx-8">
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

            <div className="auth-step-panel" key={createAccountStep}>
              {createAccountStep === "email" ? (
                <label
                  className="mt-5 grid gap-2 font-semibold"
                  htmlFor="create-account-email"
                >
                  Email
                  <input
                    autoComplete="email"
                    autoFocus
                    className="min-h-12 rounded-xl border border-border bg-background px-4 font-normal transition-colors duration-150 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-background"
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
                      autoFocus
                      className="min-h-12 rounded-xl border border-border bg-background px-4 font-normal transition-colors duration-150 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-background"
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
                      className="min-h-12 rounded-xl border border-border bg-background px-4 font-normal transition-colors duration-150 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-background"
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
                    autoFocus
                    className="min-h-12 rounded-xl border border-border bg-background px-4 font-normal transition-colors duration-150 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-background"
                    id="create-account-name"
                    maxLength={80}
                    onChange={(event) => setCreateDisplayName(event.target.value)}
                    required
                    type="text"
                    value={createDisplayName}
                  />
                </label>
              ) : null}
            </div>

            {createError ? (
              <p className="mt-4 rounded-xl border border-[#e3b6b6] bg-[#fff1f1] px-4 py-3 text-sm font-semibold text-[#8a3434]">
                {createError}
              </p>
            ) : null}

            <div className="mt-6 flex flex-wrap justify-end gap-3">
              <button
                className="inline-flex min-h-11 items-center justify-center rounded-xl border border-border bg-background px-5 font-semibold text-foreground transition-colors duration-150 hover:bg-[#f8f6f0] disabled:cursor-not-allowed disabled:opacity-60"
                disabled={isSubmitting}
                onClick={closeCreateAccount}
                type="button"
              >
                Cancel
              </button>
              <button
                className="inline-flex min-h-11 items-center justify-center rounded-xl bg-accent px-5 font-semibold text-white transition-colors duration-150 hover:bg-accent-dark disabled:cursor-not-allowed disabled:opacity-60"
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
