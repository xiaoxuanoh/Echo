"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  { href: "/", label: "Home", matches: (pathname: string) => pathname === "/" },
  {
    href: "/books",
    label: "Library",
    matches: (pathname: string) => pathname === "/books" || pathname.startsWith("/books/"),
  },
  {
    href: "/profile",
    label: "Profile",
    matches: (pathname: string) => pathname === "/profile",
  },
];

export function SiteNav() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-20 border-b border-border bg-surface/95 backdrop-blur">
      <nav
        aria-label="Main navigation"
        className="mx-auto flex min-h-16 w-full max-w-6xl items-center justify-between gap-4 px-5 sm:px-8"
      >
        <Link
          href="/"
          className="flex min-h-11 items-center text-xl font-semibold text-foreground"
        >
          Echo
        </Link>
        <div className="flex items-center gap-5 sm:gap-7">
          {navItems.map((item) => {
            const isActive = item.matches(pathname);

            return (
              <Link
                aria-current={isActive ? "page" : undefined}
                className={[
                  "inline-flex min-h-11 items-center border-b-2 text-sm font-semibold transition-colors",
                  isActive
                    ? "border-accent text-foreground"
                    : "border-transparent text-muted hover:text-foreground",
                ].join(" ")}
                href={item.href}
                key={item.href}
              >
                {item.label}
              </Link>
            );
          })}
        </div>
      </nav>
    </header>
  );
}
