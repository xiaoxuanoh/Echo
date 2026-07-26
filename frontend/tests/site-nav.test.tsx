import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SiteNav } from "@/components/navigation/site-nav";

const usePathnameMock = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => usePathnameMock(),
}));

describe("site navigation", () => {
  afterEach(() => {
    cleanup();
    usePathnameMock.mockReset();
  });

  it("links to the main sections", () => {
    usePathnameMock.mockReturnValue("/");

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
  });

  it("marks book pages as part of the library section", () => {
    usePathnameMock.mockReturnValue("/books/book-id/listen");

    render(<SiteNav />);

    expect(screen.getByRole("link", { name: "Library" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });
});
