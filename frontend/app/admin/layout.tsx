import type { ReactNode } from "react";

import { AdminNavigation } from "@/components/AdminNavigation";

export default function AdminLayout({ children }: { children: ReactNode }) {
  return (
    <section className="admin-workspace">
      <AdminNavigation />
      <div className="admin-workspace-content">{children}</div>
    </section>
  );
}
