"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  Bug,
  Database,
  Gauge,
  MessagesSquare,
  UsersRound,
  Workflow,
} from "lucide-react";

import { useAppPreferences } from "@/lib/preferences";

const adminSections = [
  { href: "/admin", label: "Overview", icon: Gauge },
  { href: "/admin/users", label: "Users", icon: UsersRound },
  { href: "/admin/feedback", label: "Feedback", icon: MessagesSquare },
  { href: "/admin/pipeline", label: "Pipeline", icon: Workflow },
  { href: "/admin/database", label: "Database", icon: Database },
  { href: "/admin/system", label: "System", icon: Activity },
  { href: "/admin/debug", label: "Debug", icon: Bug },
] as const;

export function AdminNavigation() {
  const pathname = usePathname();
  const { ui } = useAppPreferences();

  return (
    <>
      <header className="page-header admin-workspace-header">
        <h2>{ui("Administration")}</h2>
        <p>
          {ui(
            "Manage access, feedback, operations, and platform diagnostics from one workspace.",
          )}
        </p>
      </header>
      <nav className="admin-tabs" aria-label={ui("Administration sections")}>
        {adminSections.map((item) => {
          const Icon = item.icon;
          const active =
            item.href === "/admin"
              ? pathname === "/admin"
              : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className="admin-tab"
              aria-current={active ? "page" : undefined}
            >
              <Icon size={15} aria-hidden="true" />
              <span>{ui(item.label)}</span>
            </Link>
          );
        })}
      </nav>
    </>
  );
}
