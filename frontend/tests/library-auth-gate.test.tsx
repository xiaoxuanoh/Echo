import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LibraryAuthGate } from "@/components/auth/library-auth-gate";
import { getSupabaseBrowserClient } from "@/lib/supabase/browser";

vi.mock("@/components/documents/document-library", () => ({
  DocumentLibrary: () => <div>Library ready</div>,
}));

vi.mock("@/lib/supabase/browser", () => ({
  getSupabaseBrowserClient: vi.fn(),
}));

const getSupabaseBrowserClientMock = vi.mocked(getSupabaseBrowserClient);

describe("library auth gate", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("shows the library when Supabase is not configured", async () => {
    getSupabaseBrowserClientMock.mockReturnValue(null);

    render(<LibraryAuthGate />);

    expect(await screen.findByText("Library ready")).toBeInTheDocument();
    expect(screen.queryByText("Sign in to view your library")).not.toBeInTheDocument();
  });

  it("blocks library access when the user is signed out", async () => {
    const unsubscribe = vi.fn();

    getSupabaseBrowserClientMock.mockReturnValue({
      auth: {
        getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
        onAuthStateChange: vi.fn().mockReturnValue({
          data: { subscription: { unsubscribe } },
        }),
      },
    } as unknown as ReturnType<typeof getSupabaseBrowserClient>);

    render(<LibraryAuthGate />);

    expect(
      await screen.findByRole("heading", { name: "Sign in to view your library" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Sign in to view your library" }),
    ).toHaveAttribute("href", "/profile?next=%2Fbooks");
    expect(screen.queryByText("Library ready")).not.toBeInTheDocument();
  });

  it("shows the library when the user is signed in", async () => {
    const unsubscribe = vi.fn();

    getSupabaseBrowserClientMock.mockReturnValue({
      auth: {
        getSession: vi.fn().mockResolvedValue({
          data: {
            session: {
              user: {
                email: "reader@example.com",
                id: "user-id",
              },
            },
          },
        }),
        onAuthStateChange: vi.fn().mockReturnValue({
          data: { subscription: { unsubscribe } },
        }),
      },
    } as unknown as ReturnType<typeof getSupabaseBrowserClient>);

    render(<LibraryAuthGate />);

    expect(await screen.findByText("Library ready")).toBeInTheDocument();
    expect(screen.queryByText("Sign in to view your library")).not.toBeInTheDocument();
  });
});
