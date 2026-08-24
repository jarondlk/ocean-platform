import type { ReactNode } from "react";
import { LogOut } from "lucide-react";

import { auth, signOut } from "@/auth";
import { AppNavigation } from "@/components/AppNavigation";
import { PermissionGate } from "@/components/PermissionGate";
import { getCurrentUser, getLocalCurrentUser } from "@/lib/server-api";
import { localAuthDisabled } from "@/lib/security-config";

export async function AppShell({ children }: { children: ReactNode }) {
  const session = await auth();
  const authDisabled = localAuthDisabled();
  if (!session && !authDisabled) {
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
  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand-block">
          <h1>Onagawa RAG</h1>
        </div>
        <AppNavigation permissions={user.permissions} />
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
