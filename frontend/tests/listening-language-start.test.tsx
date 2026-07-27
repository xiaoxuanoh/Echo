import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ListeningLanguageStart } from "@/components/language/listening-language-start";
import { getSupabaseBrowserClient } from "@/lib/supabase/browser";

vi.mock("@/lib/supabase/browser", () => ({
  getSupabaseBrowserClient: vi.fn(),
}));

const getSupabaseBrowserClientMock = vi.mocked(getSupabaseBrowserClient);

describe("listening language start", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("asks signed-out users to sign in before library or upload actions", () => {
    getSupabaseBrowserClientMock.mockReturnValue(null);

    render(<ListeningLanguageStart />);

    expect(
      screen.getByRole("link", { name: "Sign in to view your library" }),
    ).toHaveAttribute("href", "/profile");
    expect(screen.getByRole("link", { name: "Sign in to upload" })).toHaveAttribute(
      "href",
      "/profile",
    );
    expect(
      screen.queryByRole("link", { name: "Go to library" }),
    ).not.toBeInTheDocument();
  });

  it("keeps the library and upload actions for signed-in users", async () => {
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

    render(<ListeningLanguageStart />);

    expect(await screen.findByRole("link", { name: "Go to library" })).toHaveAttribute(
      "href",
      "/books",
    );
    expect(screen.getByRole("link", { name: "Start uploading" })).toHaveAttribute(
      "href",
      "/books/new?language=cantonese",
    );
  });
});
