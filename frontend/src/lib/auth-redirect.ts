export function safeNextPath(value: string | null | undefined): string | null {
  if (!value || !value.startsWith("/") || value.startsWith("//")) {
    return null;
  }

  return value;
}

export function profileHrefForNext(nextPath: string): string {
  const safePath = safeNextPath(nextPath);
  if (!safePath) return "/profile";

  const params = new URLSearchParams({ next: safePath });
  return `/profile?${params.toString()}`;
}
