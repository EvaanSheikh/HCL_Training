import type { Metadata, Viewport } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";
import { AuthControls } from "@/components/auth-controls";

export const metadata: Metadata = {
  title: "NOHA — Autonomous Data Analyst",
  description:
    "Upload a dataset, ask a question in plain language, and review a validated answer with the analysis behind it.",
};

export const viewport: Viewport = {
  themeColor: "#f7f7f5",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body className="min-h-dvh font-sans antialiased"><div className="fixed right-5 top-4 z-50"><AuthControls /></div>{children}</body>
    </html>
  );
}
