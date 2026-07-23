"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";


const routePermissions: Array<[string, string]> = [
  ["/admin", "users:manage"],
  ["/database", "database:read"],
  ["/pipeline", "pipeline:read"],
  ["/provenance", "provenance:read"],
  ["/evaluation", "evaluation:read"],
  ["/system", "system:read"],
  ["/debug", "system:read"],
  ["/explore", "data:read"],
  ["/data", "data:read"],
  ["/analysis", "data:read"],
  ["/chat", "chat:use"],
  ["/", "overview:read"],
];

export function PermissionGate({
  children,
  permissions,
}: {
  children: ReactNode;
  permissions: string[];
}) {
  const pathname = usePathname();
  const required = routePermissions.find(([prefix]) =>
    prefix === "/" ? pathname === "/" : pathname.startsWith(prefix),
  )?.[1];
  if (required && !permissions.includes(required)) {
    return (
      <section>
        <header className="page-header">
          <h2>Access denied</h2>
        </header>
        <article className="card">
          <p className="error-text">
            Your account does not have permission to view this page.
          </p>
        </article>
      </section>
    );
  }
  return children;
}
