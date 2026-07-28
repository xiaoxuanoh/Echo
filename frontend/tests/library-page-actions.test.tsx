import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LibraryPageActions } from "@/components/auth/library-page-actions";
import { getSupabaseBrowserClient } from "@/lib/supabase/browser";

vi.mock("@/lib/supabase/browser", () => ({
  getSupabaseBrowserClient: vi.fn(),
}));

const getSupabaseBrowserClientMock = vi.mocked(getSupabaseBrowserClient);

describe("library page actions", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("hides library actions when the user is signed out", () => {
    getSupabaseBrowserClientMock.mockReturnValue(null);

    render(<LibraryPageActions />);

    expect(
      screen.queryByRole("link", { name: "Upload new file" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Main page" }),
    ).not.toBeInTheDocument();
  });

  it("shows library actions when the user is signed in", async () => {
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

    render(<LibraryPageActions />);

    expect(await screen.findByRole("link", { name: "Upload new file" })).toHaveAttribute(
      "href",
      "/books/new",
    );
    expect(screen.getByRole("link", { name: "Main page" })).toHaveAttribute(
      "href",
      "/",
    );
  });
});
