"use client";
import { useEffect, useRef, useState } from "react";
import { useChatIdentity } from "@/components/ChatIdentityProvider";
import { decodeSettings, defaultScope, defaultSettings, encodeSettings, scopeErrors, settingsErrors, settingsStorageKey, type ChatSettings } from "./chat-settings";
import type { EvidenceScope } from "./generated/chat-scope";

export function useChatSettings(transientAnalysisId: string) {
  const savedScope = useRef(defaultScope());
  const accountId = useChatIdentity();
  const [settings, setSettings] = useState<ChatSettings>({...defaultSettings});
  const [scope, setScope] = useState<EvidenceScope>(defaultScope);
  const [hydratedAccount, setHydratedAccount] = useState<string | null>(null);
  const ready = !!accountId && hydratedAccount === accountId;
  const [blocked, setBlocked] = useState("");
  const [storageNotice, setStorageNotice] = useState("");
  useEffect(() => {
    setHydratedAccount(null);
    setSettings({...defaultSettings}); setScope(defaultScope());
    savedScope.current = defaultScope();
    setBlocked(""); setStorageNotice("");
    if (!accountId) return;
    let raw: string | null;
    try { raw = window.localStorage.getItem(settingsStorageKey(accountId)); }
    catch { setStorageNotice("Settings are available for this session; browser storage is unavailable."); setHydratedAccount(accountId); return; }
    try { const saved = decodeSettings(raw); setSettings(saved.settings); setScope(saved.scope); savedScope.current = saved.scope; }
    catch { setBlocked("Saved source settings need review. Reset settings to continue."); }
    setHydratedAccount(accountId);
  }, [accountId]);
  useEffect(() => {
    if (!ready || !accountId || blocked || scopeErrors(scope).length || settingsErrors(settings).length) return;
    if (!transientAnalysisId) savedScope.current = scope;
    try { window.localStorage.setItem(settingsStorageKey(accountId), encodeSettings(settings, transientAnalysisId ? savedScope.current : scope)); }
    catch { setStorageNotice("Settings are available for this session; browser storage is unavailable."); }
  }, [accountId, ready, blocked, scope, settings, transientAnalysisId]);
  function reset(model: string) {
    savedScope.current = defaultScope();
    setSettings({...defaultSettings, model}); setScope(defaultScope()); setBlocked("");
  }
  // Identity can change before its hydration effect runs. Do not expose the
  // previous account's scientific scope during that render or persist it.
  return {settings: ready ? settings : {...defaultSettings}, setSettings,
    scope: ready ? scope : defaultScope(), setScope, ready,
    blocked: ready ? blocked : "", storageNotice: ready ? storageNotice : "", reset};
}
