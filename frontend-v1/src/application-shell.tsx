"use client";

import { useCallback, useEffect, useId, useRef, useState, type ReactNode, type RefObject } from "react";
import { Menu, X } from "lucide-react";
import type { Locale } from "./model";
import "./shell.css";

export type ShellLink = { id: string; href: string; label: string; icon?: ReactNode };

export function ShellWordmark({ onHome, href = "/" }: { onHome?: () => void; href?: string }) {
  const wordmark = <span>OCEAN<span className="brand-subtitle">Platform</span></span>;
  return onHome
    ? <button className="brand" onClick={onHome} aria-label="OCEAN Platform">{wordmark}</button>
    : <a className="brand" href={href} aria-label="OCEAN Platform">{wordmark}</a>;
}

export function ShellNavigation({ links, current, locale, onNavigate }: {
  links: readonly ShellLink[]; current: string; locale: Locale; onNavigate?: (link: ShellLink) => void;
}) {
  return <nav className="primary-nav" aria-label={locale === "en" ? "Primary navigation" : "メインナビゲーション"}>
    {links.map((link) => <a key={link.id} href={link.href} aria-current={current === link.id ? "page" : undefined} onClick={(event) => {
      if (!onNavigate || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault(); onNavigate(link);
    }}>{link.icon}<span>{link.label}</span></a>)}
  </nav>;
}

export function ShellHeader({ locale, drawerOpen, onMenu, onHome, navigation, actions, inert = false }: {
  locale: Locale; drawerOpen: boolean; onMenu: () => void; onHome?: () => void;
  navigation: ReactNode; actions: ReactNode; inert?: boolean;
}) {
  return <header className="topbar" inert={inert}>
    <button className="mobile-menu icon-button" onClick={onMenu} aria-label={locale === "en" ? "Open navigation" : "ナビゲーションを開く"} aria-expanded={drawerOpen} aria-controls="app-sidebar"><Menu size={20} /></button>
    <ShellWordmark onHome={onHome} />{navigation}<div className="topbar-actions">{actions}</div>
  </header>;
}

export function ShellSidebarFrame({ open, label, locale, onClose, children, sidebarRef, footer }: {
  open: boolean; label: string; locale: Locale; onClose: () => void; children: ReactNode;
  sidebarRef?: RefObject<HTMLElement | null>; footer?: ReactNode;
}) {
  return <aside id="app-sidebar" ref={sidebarRef} role={open ? "dialog" : undefined} aria-modal={open ? true : undefined} className={`sidebar ${open ? "drawer-open" : ""}`} aria-label={label}>
    <div className="drawer-header"><span>{locale === "en" ? "Navigation" : "ナビゲーション"}</span><button className="icon-button" aria-label={locale === "en" ? "Close navigation" : "ナビゲーションを閉じる"} onClick={onClose}><X size={18} /></button></div>
    {children}{footer}
  </aside>;
}

const focusable = 'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex="0"]';

function useFocusBoundary(open: boolean, panel: RefObject<HTMLElement | null>, onClose: () => void) {
  const close = useRef(onClose); close.current = onClose;
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const items = () => Array.from(panel.current?.querySelectorAll<HTMLElement>(focusable) ?? []).filter((item) => item.getClientRects().length > 0);
    const frame = requestAnimationFrame(() => (items()[0] ?? panel.current)?.focus());
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); close.current(); }
      if (event.key === "Tab") {
        const list = items(); const first = list[0]; const last = list.at(-1);
        if (!first) { event.preventDefault(); return; }
        if (event.shiftKey && (document.activeElement === first || !panel.current?.contains(document.activeElement))) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && (document.activeElement === last || !panel.current?.contains(document.activeElement))) { event.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", keydown);
    return () => { cancelAnimationFrame(frame); document.removeEventListener("keydown", keydown); if (previous?.isConnected) previous.focus(); };
  }, [open, panel]);
}

export function ShellDialog({ title, locale, onClose, children }: { title: string; locale: Locale; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null); const id = useId();
  useFocusBoundary(true, ref, onClose);
  return <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><div ref={ref} className="modal" role="dialog" aria-modal="true" aria-labelledby={id} tabIndex={-1}>
    <header><h2 id={id}>{title}</h2><button className="icon-button" aria-label={locale === "en" ? "Close" : "閉じる"} onClick={onClose}><X size={18} /></button></header>{children}
  </div></div>;
}

/** Shell slots own presentation and focus only; scientific state stays with consumers. */
export function ApplicationShell({ locale, current, primaryLinks, onNavigate, onHome, actions, sidebar, children, notice, dialogOpen = false }: {
  locale: Locale; current: string; primaryLinks: readonly ShellLink[]; onNavigate: (link: ShellLink) => void;
  onHome: () => void; actions: ReactNode; sidebar: ReactNode; children: ReactNode; notice?: ReactNode; dialogOpen?: boolean;
}) {
  const [drawerOpen, setDrawerOpen] = useDrawerState();
  const sidebarRef = useRef<HTMLElement>(null);
  useFocusBoundary(drawerOpen, sidebarRef, () => setDrawerOpen(false));
  useEffect(() => { setDrawerOpen(false); }, [current, setDrawerOpen]);
  useEffect(() => { if (dialogOpen) setDrawerOpen(false); }, [dialogOpen, setDrawerOpen]);
  const navigate = (link: ShellLink) => { onNavigate(link); setDrawerOpen(false); };
  return <div className="app runtime-shell" inert={dialogOpen}>
    <a className="skip-link" inert={drawerOpen} href="#main-content">{locale === "en" ? "Skip to content" : "コンテンツへ移動"}</a>
    <ShellHeader locale={locale} drawerOpen={drawerOpen} onMenu={() => setDrawerOpen(!drawerOpen)} onHome={onHome} inert={drawerOpen}
      navigation={<ShellNavigation locale={locale} current={current} links={primaryLinks} onNavigate={navigate} />} actions={actions} />
    {notice && <div className="runtime-notice" inert={drawerOpen}>{notice}</div>}
    <div className="app-body">
      {drawerOpen && <button className="drawer-scrim" tabIndex={-1} aria-label={locale === "en" ? "Close navigation" : "ナビゲーションを閉じる"} onClick={() => setDrawerOpen(false)} />}
      <ShellSidebarFrame sidebarRef={sidebarRef} open={drawerOpen} label={locale === "en" ? "Application navigation" : "アプリケーションナビゲーション"} locale={locale} onClose={() => setDrawerOpen(false)}>
        <div onClick={(event) => { if ((event.target as HTMLElement).closest("a[href]")) setDrawerOpen(false); }}>{sidebar}</div>
      </ShellSidebarFrame>
      <main id="main-content" className="main-content runtime-main" tabIndex={-1} inert={drawerOpen}>{children}</main>
    </div>
  </div>;
}

// Kept separate from consumer state and from persisted presentation choices.
function useDrawerState() {
  const [open, setOpen] = useState(false);
  const set = useCallback((next: boolean) => setOpen(next), []);
  useEffect(() => {
    const media = window.matchMedia("(min-width: 761px)");
    const close = () => { if (media.matches) setOpen(false); };
    media.addEventListener("change", close); return () => media.removeEventListener("change", close);
  }, []);
  return [open, set] as const;
}
