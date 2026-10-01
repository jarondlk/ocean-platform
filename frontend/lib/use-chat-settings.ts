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
  const [ready, setReady] = useState(false);
  const [blocked, setBlocked] = useState("");
  const [storageNotice, setStorageNotice] = useState("");
  useEffect(() => {
    if (!accountId) return;
    let raw: string | null;
    try { raw = window.localStorage.getItem(settingsStorageKey(accountId)); }
    catch { setStorageNotice("Settings are available for this session; browser storage is unavailable."); setReady(true); return; }
    try { const saved = decodeSettings(raw); setSettings(saved.settings); setScope(saved.scope); savedScope.current = saved.scope; }
    catch { setBlocked("Saved source settings need review. Reset settings to continue."); }
    setReady(true);
  }, [accountId]);
  useEffect(() => {
    if (!ready || !accountId || blocked || scopeErrors(scope).length || settingsErrors(settings).length) return;
    if (!transientAnalysisId) savedScope.current = scope;
    try { window.localStorage.setItem(settingsStorageKey(accountId), encodeSettings(settings, transientAnalysisId ? savedScope.current : scope)); }
    catch { setStorageNotice("Settings are available for this session; browser storage is unavailable."); }
  }, [accountId, ready, blocked, scope, settings, transientAnalysisId]);
  function reset(model: string) {
    setSettings({...defaultSettings, model}); setScope(defaultScope()); setBlocked("");
  }
  return {settings, setSettings, scope, setScope, ready, blocked, storageNotice, reset};
}
