import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import { AppShell } from "@/components/AppShell";
import { PRODUCT_DESCRIPTION, PRODUCT_NAME } from "@/lib/brand";
import { AppPreferencesProvider } from "@/lib/preferences";

export const metadata: Metadata = {
  title: PRODUCT_NAME,
  description: PRODUCT_DESCRIPTION,
  manifest: "/manifest.webmanifest",
  icons: {
    icon: "/favicon.svg",
  },
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
