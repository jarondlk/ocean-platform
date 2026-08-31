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
    icon: UsersRound,
  },
  {
    href: "/admin/feedback",
    label: "Feedback",
    icon: MessagesSquare,
  },
  {
    href: "/admin/pipeline",
    label: "Pipeline",
    icon: Workflow,
  },
  {
    href: "/admin/database",
    label: "Database",
    icon: Database,
  },
  {
    href: "/admin/system",
    label: "System",
    icon: Activity,
  },
  {
    href: "/admin/debug",
    label: "Debug",
    icon: Bug,
  },
] as const;

export default function AdminOverviewPage() {
  const { ui } = useAppPreferences();

  return (
    <section className="admin-overview">
      <div className="admin-section-grid">
        {sections.map((item) => {
          const Icon = item.icon;
          return (
            <Link className="admin-section-card" href={item.href} key={item.href}>
              <span className="admin-section-icon">
                <Icon size={18} aria-hidden="true" />
              </span>
              <strong>{ui(item.label)}</strong>
              <ArrowRight size={16} aria-hidden="true" />
            </Link>
          );
        })}
      </div>
    </section>
  );
}
