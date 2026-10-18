import type { ReactNode } from "react";
import "../../../app/globals.css";

export default function DevelopmentLayout({ children }: { children: ReactNode }) {
  return <html lang="en" suppressHydrationWarning><body>{children}</body></html>;
}
