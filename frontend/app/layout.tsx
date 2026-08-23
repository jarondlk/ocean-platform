import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import { AppShell } from "@/components/AppShell";
import { AppPreferencesProvider } from "@/lib/preferences";

export const metadata: Metadata = {
  title: "Onagawa Source Chat",
  description: "Academic interface for provenance-aware marine environmental RAG.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <AppPreferencesProvider>
          <AppShell>{children}</AppShell>
        </AppPreferencesProvider>
      </body>
    </html>
  );
}
