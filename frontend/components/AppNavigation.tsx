"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOpen, ChartNoAxesColumn, ClipboardCheck, Database, Fingerprint, MessageSquare, Settings, ShieldCheck } from "lucide-react";

import { useAppPreferences } from "@/lib/preferences";

const navItems = [
  { href: "/", key: "overview", icon: BookOpen, permission: "overview:read" },
  { href: "/explore", key: "explore", icon: ChartNoAxesColumn, permission: "data:read" },
  { href: "/data", key: "data", icon: Database, permission: "data:read" },
  { href: "/provenance", key: "provenance", icon: Fingerprint, permission: "provenance:read" },
  { href: "/evaluation", key: "evaluation", icon: ClipboardCheck, permission: "evaluation:read" },
  { href: "/chat", key: "chat", icon: MessageSquare, permission: "chat:use" },
  { href: "/admin", key: "admin", icon: ShieldCheck, permission: "users:manage" },
  { href: "/settings", key: "settings", icon: Settings, permission: "overview:read" },
] as const;

export function AppNavigation({ permissions }: { permissions: string[] }) {
  const pathname = usePathname();
  const { t } = useAppPreferences();
  return (
    <nav className="nav-list" aria-label="Primary navigation">
      {navItems.filter((item) => permissions.includes(item.permission)).map((item) => {
        const Icon = item.icon;
        const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
        return (
          <Link key={item.href} href={item.href} className="nav-link" aria-current={active ? "page" : undefined}>
            <Icon size={16} aria-hidden="true" />
            <span>{t("nav", item.key)}</span>
          </Link>
        );
      })}
    </nav>
  );
}
