import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Echo - Spoken documents",
  description: "Turn your documents into spoken language.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="flex min-h-full flex-col">{children}</body>
    </html>
  );
}
