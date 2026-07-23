import Link from "next/link";
import type { ReactNode } from "react";
import { Activity, BookOpen, Bug, ChartNoAxesColumn, ClipboardCheck, Database, Fingerprint, LogOut, MessageSquare, MessagesSquare, TableProperties, UsersRound, Workflow } from "lucide-react";

import { auth, signOut } from "@/auth";
import { PermissionGate } from "@/components/PermissionGate";
import { getCurrentUser, getLocalCurrentUser } from "@/lib/server-api";

const navItems = [
  { href: "/", label: "Overview", icon: BookOpen, permission: "overview:read" },
  { href: "/explore", label: "Explore", icon: ChartNoAxesColumn, permission: "data:read" },
  { href: "/data", label: "Data", icon: Database, permission: "data:read" },
  { href: "/database", label: "Database", icon: TableProperties, permission: "database:read" },
  { href: "/pipeline", label: "Pipeline", icon: Workflow, permission: "pipeline:read" },
  { href: "/provenance", label: "Provenance", icon: Fingerprint, permission: "provenance:read" },
  { href: "/evaluation", label: "Evaluation", icon: ClipboardCheck, permission: "evaluation:read" },
  { href: "/chat", label: "Chat", icon: MessageSquare, permission: "chat:use" },
  { href: "/system", label: "System", icon: Activity, permission: "system:read" },
  { href: "/debug", label: "Debug", icon: Bug, permission: "system:read" },
  { href: "/admin/feedback", label: "Feedback", icon: MessagesSquare, permission: "feedback:review" },
  { href: "/admin/users", label: "Users", icon: UsersRound, permission: "users:manage" },
];

export async function AppShell({ children }: { children: ReactNode }) {
  const session = await auth();
  const localAuthDisabled =
    process.env.AUTH_MODE?.trim().toLowerCase() === "disabled";
  if (!session && !localAuthDisabled) {
    return <main className="auth-main">{children}</main>;
  }
  const user = session
    ? await getCurrentUser(session)
    : await getLocalCurrentUser();
  if (!user) {
    return (
      <main className="auth-main">
        <section className="login-page">
          <article className="card login-card">
            <h2>Account access unavailable</h2>
            <p className="error-text">
              Your invitation may have expired, or this account may be suspended.
            </p>
            <form
              action={async () => {
                "use server";
                await signOut({ redirectTo: "/login" });
              }}
            >
              <button className="button" type="submit">Sign out</button>
            </form>
          </article>
        </section>
      </main>
    );
  }
  const permissions = new Set(user.permissions);
  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand-block">
          <h1>Onagawa RAG</h1>
        </div>
        <nav className="nav-list">
          {navItems.filter((item) => permissions.has(item.permission)).map((item) => {
            const Icon = item.icon;
            return (
              <Link key={item.href} href={item.href} className="nav-link">
                <Icon size={16} aria-hidden="true" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-user">
          <div>
            <strong>{user.display_name || user.email}</strong>
            <span>{user.role} · {user.account_type}</span>
          </div>
          {session ? (
            <form
              action={async () => {
                "use server";
                await signOut({ redirectTo: "/login" });
              }}
            >
              <button className="icon-button" type="submit" title="Sign out">
                <LogOut size={16} aria-hidden="true" />
                <span className="sr-only">Sign out</span>
              </button>
            </form>
          ) : null}
        </div>
      </aside>
      <main className="main-panel">
        <PermissionGate permissions={user.permissions}>{children}</PermissionGate>
      </main>
    </div>
  );
}
