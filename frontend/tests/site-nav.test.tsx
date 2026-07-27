import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SiteNav } from "@/components/navigation/site-nav";
import { getSupabaseBrowserClient } from "@/lib/supabase/browser";

const usePathnameMock = vi.fn();
const getSupabaseBrowserClientMock = vi.mocked(getSupabaseBrowserClient);

vi.mock("next/navigation", () => ({
  usePathname: () => usePathnameMock(),
}));

vi.mock("@/lib/supabase/browser", () => ({
  getSupabaseBrowserClient: vi.fn(),
}));

describe("site navigation", () => {
  afterEach(() => {
    cleanup();
    usePathnameMock.mockReset();
    vi.clearAllMocks();
  });

  it("links to the main sections", () => {
    usePathnameMock.mockReturnValue("/");
    getSupabaseBrowserClientMock.mockReturnValue(null);

    render(<SiteNav />);

    expect(screen.getByRole("link", { name: "Echo" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Library" })).toHaveAttribute(
      "href",
      "/books",
    );
    expect(screen.getByRole("link", { name: "Profile" })).toHaveAttribute(
      "href",
      "/profile",
    );
    expect(screen.getByLabelText("Signed out")).toBeInTheDocument();
  });

  it("marks document pages as part of the library section", () => {
    usePathnameMock.mockReturnValue("/books/document-id/listen");
    getSupabaseBrowserClientMock.mockReturnValue(null);

    render(<SiteNav />);

    expect(screen.getByRole("link", { name: "Library" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("shows a signed-in indicator when a session exists", async () => {
    const unsubscribe = vi.fn();

    usePathnameMock.mockReturnValue("/profile");
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

    render(<SiteNav />);

    expect(await screen.findByLabelText("Signed in")).toBeInTheDocument();
    expect(screen.getByText("Signed in")).toBeInTheDocument();
  });
});
