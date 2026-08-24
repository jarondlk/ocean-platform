"use client";

import Link from "next/link";
import {
  Activity,
  ArrowRight,
  Bug,
  Database,
  MessagesSquare,
  UsersRound,
  Workflow,
} from "lucide-react";

import { useAppPreferences } from "@/lib/preferences";

const sections = [
  {
    href: "/admin/users",
    label: "Users",
    description: "Invite users and manage account roles, types, and status.",
    icon: UsersRound,
  },
  {
    href: "/admin/feedback",
    label: "Feedback",
    description: "Review answer ratings, comments, evidence, and trust reports.",
    icon: MessagesSquare,
  },
  {
    href: "/admin/pipeline",
    label: "Pipeline",
    description: "Run and monitor ingestion, analysis, database, and embedding jobs.",
    icon: Workflow,
  },
  {
    href: "/admin/database",
    label: "Database",
    description: "Inspect PostgreSQL schema, table contents, and read-only queries.",
    icon: Database,
  },
  {
    href: "/admin/system",
    label: "System",
    description: "Monitor service health, artifacts, models, and corpus coverage.",
    icon: Activity,
  },
  {
    href: "/admin/debug",
    label: "Debug",
    description: "Inspect raw application, environment, route, cache, and client state.",
    icon: Bug,
  },
] as const;

export default function AdminOverviewPage() {
  const { ui } = useAppPreferences();

  return (
    <section className="admin-overview">
      <header className="admin-overview-intro">
        <h3>{ui("Admin overview")}</h3>
        <p>
          {ui(
            "Choose a section to manage the application without leaving the administration workspace.",
          )}
        </p>
      </header>
      <div className="admin-section-grid">
        {sections.map((item) => {
          const Icon = item.icon;
          return (
            <Link className="admin-section-card" href={item.href} key={item.href}>
              <span className="admin-section-icon">
                <Icon size={18} aria-hidden="true" />
              </span>
              <span className="admin-section-copy">
                <strong>{ui(item.label)}</strong>
                <span>{ui(item.description)}</span>
              </span>
              <ArrowRight size={16} aria-hidden="true" />
            </Link>
          );
        })}
      </div>
    </section>
  );
}
