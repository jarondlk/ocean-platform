import Link from "next/link";
import type { ReactNode } from "react";
import { Activity, BookOpen, Bug, ChartNoAxesColumn, ClipboardCheck, Database, Fingerprint, MessageSquare, TableProperties, Workflow } from "lucide-react";

const navItems = [
  { href: "/", label: "Overview", icon: BookOpen },
  { href: "/explore", label: "Explore", icon: ChartNoAxesColumn },
  { href: "/data", label: "Data", icon: Database },
  { href: "/database", label: "Database", icon: TableProperties },
  { href: "/pipeline", label: "Pipeline", icon: Workflow },
  { href: "/provenance", label: "Provenance", icon: Fingerprint },
  { href: "/evaluation", label: "Evaluation", icon: ClipboardCheck },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/system", label: "System", icon: Activity },
  { href: "/debug", label: "Debug", icon: Bug },
];

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand-block">
          <h1>Onagawa RAG</h1>
        </div>
        <nav className="nav-list">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <Link key={item.href} href={item.href} className="nav-link">
                <Icon size={16} aria-hidden="true" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </aside>
      <main className="main-panel">{children}</main>
    </div>
  );
}
