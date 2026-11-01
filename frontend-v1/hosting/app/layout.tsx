import type { Metadata } from "next";
import type { ReactNode } from "react";
import "../../app/globals.css";

export const metadata: Metadata = { title: "OCEAN Platform", description: "Independent OCEAN research workspace", robots: { index: false, follow: false } };
export default function HostLayout({ children }: { children: ReactNode }) {
  return <html lang="en" suppressHydrationWarning><body>{children}</body></html>;
}
