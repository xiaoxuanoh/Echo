import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
        signOut: vi.fn(),
        signUp: vi.fn(),
      },
    } as unknown as ReturnType<typeof getSupabaseBrowserClient>);

    render(<AuthPanel />);

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "reader@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "correct-password" },
    });
    fireEvent.click(screen.getAllByRole("button", { name: "Sign in" })[1]);

    await waitFor(() => {
      expect(signInWithPassword).toHaveBeenCalledWith({
        email: "reader@example.com",
        password: "correct-password",
      });
    });
    expect(await screen.findByText("reader@example.com")).toBeInTheDocument();
  });
});
