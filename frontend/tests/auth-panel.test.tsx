import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthPanel } from "@/components/auth/auth-panel";
import { getSupabaseBrowserClient } from "@/lib/supabase/browser";

vi.mock("@/lib/supabase/browser", () => ({
  getSupabaseBrowserClient: vi.fn(),
}));

const getSupabaseBrowserClientMock = vi.mocked(getSupabaseBrowserClient);

describe("auth panel", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("explains the required Supabase configuration when env is missing", () => {
    getSupabaseBrowserClientMock.mockReturnValue(null);

    render(<AuthPanel />);

    expect(screen.getByText("Supabase Auth")).toBeInTheDocument();
    expect(
      screen.getByText("Sign in is not available until the local Supabase settings are added."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY/),
    ).toBeInTheDocument();
  });

  it("signs in with email and password", async () => {
    const signInWithPassword = vi.fn().mockResolvedValue({
      data: {
        session: {
          user: {
            email: "reader@example.com",
            id: "user-id",
          },
        },
      },
      error: null,
    });
    const unsubscribe = vi.fn();

    getSupabaseBrowserClientMock.mockReturnValue({
      auth: {
        getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
        onAuthStateChange: vi.fn().mockReturnValue({
          data: { subscription: { unsubscribe } },
        }),
        signInWithPassword,
        resetPasswordForEmail: vi.fn(),
        signOut: vi.fn(),
        signUp: vi.fn(),
        updateUser: vi.fn(),
      },
    } as unknown as ReturnType<typeof getSupabaseBrowserClient>);

    render(<AuthPanel />);

    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "reader@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByText("reader@example.com")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "correct-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(signInWithPassword).toHaveBeenCalledWith({
        email: "reader@example.com",
        password: "correct-password",
      });
    });
    expect(await screen.findByText("User information")).toBeInTheDocument();
    expect(screen.getByText("Email address")).toBeInTheDocument();
    expect(screen.getByText("reader@example.com")).toBeInTheDocument();
    expect(screen.getByText("Name not set yet")).toBeInTheDocument();
    expect(screen.getByText("Ready for cloud sync")).toBeInTheDocument();
    expect(screen.getByText("Technical details")).toBeInTheDocument();
  });

  it("shows user information instead of the sign-in form when already signed in", async () => {
    const unsubscribe = vi.fn();

    getSupabaseBrowserClientMock.mockReturnValue({
      auth: {
        getSession: vi.fn().mockResolvedValue({
          data: {
            session: {
              user: {
                email: "reader@example.com",
                id: "user-id",
                user_metadata: {
                  display_name: "Reader",
                },
              },
            },
          },
        }),
        onAuthStateChange: vi.fn().mockReturnValue({
          data: { subscription: { unsubscribe } },
        }),
        signInWithPassword: vi.fn(),
        resetPasswordForEmail: vi.fn(),
        signOut: vi.fn(),
        signUp: vi.fn(),
        updateUser: vi.fn(),
      },
    } as unknown as ReturnType<typeof getSupabaseBrowserClient>);

    render(<AuthPanel />);

    expect(await screen.findByText("User information")).toBeInTheDocument();
    expect(screen.getByText("Welcome, Reader.")).toBeInTheDocument();
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Reader")).toBeInTheDocument();
    expect(screen.getByText("Email address")).toBeInTheDocument();
    expect(screen.getByText("reader@example.com")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
    expect(screen.getByText("Technical details")).toBeInTheDocument();
    expect(screen.getByText("Account provider")).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Sign in" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Create account" }),
    ).not.toBeInTheDocument();
  });

  it("asks new users to confirm their email before signing in", async () => {
    const signUp = vi.fn().mockResolvedValue({
      data: {
        session: null,
      },
      error: null,
    });
    const unsubscribe = vi.fn();

    getSupabaseBrowserClientMock.mockReturnValue({
      auth: {
        getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
        onAuthStateChange: vi.fn().mockReturnValue({
          data: { subscription: { unsubscribe } },
        }),
        signInWithPassword: vi.fn(),
        resetPasswordForEmail: vi.fn(),
        signOut: vi.fn(),
        signUp,
        updateUser: vi.fn(),
      },
    } as unknown as ReturnType<typeof getSupabaseBrowserClient>);

    render(<AuthPanel />);

    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    let dialog = screen.getByRole("dialog", { name: "What is your email?" });
    fireEvent.change(within(dialog).getByLabelText("Email"), {
      target: { value: "new-reader@example.com" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Continue" }));

    dialog = screen.getByRole("dialog", { name: "Create a password" });
    fireEvent.change(within(dialog).getByLabelText("Password"), {
      target: { value: "correct-password" },
    });
    fireEvent.change(within(dialog).getByLabelText("Confirm password"), {
      target: { value: "correct-password" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Continue" }));

    dialog = screen.getByRole("dialog", { name: "What should Echo call you?" });
    fireEvent.change(within(dialog).getByLabelText("Name"), {
      target: { value: "New Reader" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create account" }));

    await waitFor(() => {
      expect(signUp).toHaveBeenCalledWith({
        email: "new-reader@example.com",
        password: "correct-password",
        options: {
          data: {
            display_name: "New Reader",
          },
        },
      });
    });
    expect(
      await screen.findByText(/We sent a confirmation link to/),
    ).toBeInTheDocument();
    expect(screen.getByText("new-reader@example.com")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveValue("new-reader@example.com");
    expect(screen.queryByText("User information")).not.toBeInTheDocument();
  });

  it("sends a password reset email from the password step", async () => {
    const resetPasswordForEmail = vi.fn().mockResolvedValue({
      data: {},
      error: null,
    });
    const unsubscribe = vi.fn();

    getSupabaseBrowserClientMock.mockReturnValue({
      auth: {
        getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
        onAuthStateChange: vi.fn().mockReturnValue({
          data: { subscription: { unsubscribe } },
        }),
        signInWithPassword: vi.fn(),
        resetPasswordForEmail,
        signOut: vi.fn(),
        signUp: vi.fn(),
        updateUser: vi.fn(),
      },
    } as unknown as ReturnType<typeof getSupabaseBrowserClient>);

    render(<AuthPanel />);

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "reader@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.click(await screen.findByRole("button", { name: "Forgot password?" }));

    await waitFor(() => {
      expect(resetPasswordForEmail).toHaveBeenCalledWith("reader@example.com", {
        redirectTo: "http://localhost:3000/profile",
      });
    });
    expect(
      await screen.findByText(/We sent a password reset link to/),
    ).toBeInTheDocument();
    expect(screen.getAllByText("reader@example.com")).toHaveLength(2);
  });

  it("lets users choose a new password after a recovery link", async () => {
    const updateUser = vi.fn().mockResolvedValue({
      data: {
        user: {
          email: "reader@example.com",
          id: "user-id",
        },
      },
      error: null,
    });
    const unsubscribe = vi.fn();
    const session = {
      user: {
        email: "reader@example.com",
        id: "user-id",
      },
    };

    getSupabaseBrowserClientMock.mockReturnValue({
      auth: {
        getSession: vi.fn().mockResolvedValue({ data: { session } }),
        onAuthStateChange: vi.fn((callback) => {
          callback("PASSWORD_RECOVERY", session);

          return {
            data: { subscription: { unsubscribe } },
          };
        }),
        signInWithPassword: vi.fn(),
        resetPasswordForEmail: vi.fn(),
        signOut: vi.fn(),
        signUp: vi.fn(),
        updateUser,
      },
    } as unknown as ReturnType<typeof getSupabaseBrowserClient>);

    render(<AuthPanel />);

    expect(
      await screen.findByRole("heading", { name: "Choose a new password" }),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("New password"), {
      target: { value: "new-password" },
    });
    fireEvent.change(screen.getByLabelText("Confirm new password"), {
      target: { value: "new-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Update password" }));

    await waitFor(() => {
      expect(updateUser).toHaveBeenCalledWith({
        password: "new-password",
      });
    });
    expect(await screen.findByText("Your password has been updated.")).toBeInTheDocument();
  });
});
