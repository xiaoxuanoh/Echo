"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";

import { useAuthSession } from "@/components/auth/use-auth-session";

const primaryNavItems = [
  { href: "/", label: "Home", matches: (pathname: string) => pathname === "/" },
  {
    href: "/books",
    label: "Library",
    matches: (pathname: string) => pathname === "/books" || pathname.startsWith("/books/"),
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
          aria-label="Echo"
          href="/"
          className="flex min-h-11 shrink-0 items-center"
        >
          <Image
            alt=""
            aria-hidden="true"
            className="hidden h-10 w-auto sm:block"
            height={320}
            priority
            src="/brand/echo-horizontal.svg"
            width={1200}
          />
          <span aria-hidden="true" className="flex items-center gap-2 sm:hidden">
            <Image
              alt=""
              aria-hidden="true"
              className="h-7 w-7"
              height={512}
              src="/brand/echo-icon.svg"
              width={512}
            />
            <span className="text-lg font-semibold text-foreground">Echo</span>
          </span>
        </Link>
        <div className="flex items-center gap-4 sm:gap-6">
          {primaryNavItems.map((item) => {
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
          {isSignedIn ? (
            <>
              <Link
                aria-current={pathname === "/profile" ? "page" : undefined}
                className={[
                  "relative inline-flex min-h-11 items-center text-sm font-semibold transition-colors after:absolute after:right-0 after:bottom-0 after:left-0 after:h-0.5 after:origin-center after:bg-accent after:transition-transform after:duration-300",
                  pathname === "/profile"
                    ? "text-foreground after:scale-x-100"
                    : "text-muted after:scale-x-0 hover:text-foreground hover:after:scale-x-100",
                ].join(" ")}
                href="/profile"
              >
                Profile
              </Link>
              <span
                aria-label="Signed in"
                className="inline-flex min-h-9 items-center gap-2 rounded-full border border-[#b9d2c1] bg-[#ecf6ef] px-3 text-xs font-semibold text-[#28543a]"
              >
                <span
                  aria-hidden="true"
                  className="h-2 w-2 rounded-full bg-[#2f8f4e]"
                />
                Signed in
              </span>
            </>
          ) : (
            <Link
              aria-current={pathname === "/profile" ? "page" : undefined}
              className="inline-flex min-h-10 items-center justify-center rounded-xl bg-accent px-4 text-sm font-semibold text-white shadow-sm transition-colors duration-150 hover:bg-accent-dark"
              href="/profile"
            >
              Sign in
            </Link>
          )}
        </div>
      </nav>
    </header>
  );
}
