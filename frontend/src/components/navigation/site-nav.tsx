"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuthSession } from "@/components/auth/use-auth-session";

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
  const { isSignedIn } = useAuthSession();

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
        <div className="flex items-center gap-4 sm:gap-6">
          {navItems.map((item) => {
            const isActive = item.matches(pathname);

            return (
              <Link
                aria-current={isActive ? "page" : undefined}
                className={[
                  "relative inline-flex min-h-11 items-center text-sm font-semibold transition-colors after:absolute after:right-0 after:bottom-0 after:left-0 after:h-0.5 after:origin-center after:bg-accent after:transition-transform after:duration-300",
                  isActive
                    ? "text-foreground after:scale-x-100"
                    : "text-muted after:scale-x-0 hover:text-foreground hover:after:scale-x-100",
                ].join(" ")}
                href={item.href}
                key={item.href}
              >
                {item.label}
              </Link>
            );
          })}
          <span
            aria-label={isSignedIn ? "Signed in" : "Signed out"}
            className={[
              "inline-flex min-h-9 items-center gap-2 rounded-full border px-3 text-xs font-semibold",
              isSignedIn
                ? "border-[#b9d2c1] bg-[#ecf6ef] text-[#28543a]"
                : "border-[#e3b6b6] bg-[#fff1f1] text-[#8a3434]",
            ].join(" ")}
          >
            <span
              aria-hidden="true"
              className={[
                "h-2 w-2 rounded-full",
                isSignedIn ? "bg-[#2f8f4e]" : "bg-[#c94a4a]",
              ].join(" ")}
            />
            {isSignedIn ? "Signed in" : "Signed out"}
          </span>
        </div>
      </nav>
    </header>
  );
}
