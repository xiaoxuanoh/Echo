import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Echo — Traditional Chinese books in Cantonese",
  description: "Turn Traditional Chinese books into Cantonese audio.",
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
