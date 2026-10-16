import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Harness v2 · Transcript",
  description: "Build a lecture's transcript from a book, every step and call visible.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
