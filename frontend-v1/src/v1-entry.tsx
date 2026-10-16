"use client";

import { lazy, Suspense, useEffect, useState } from "react";
import type { Location } from "./model";
import { loadRuntimeMode, type RuntimeMode } from "./runtime";
import { RuntimeApp } from "./runtime-app";

// Only the explicitly selected local preview loads P00's simulation dependency
// graph. A failed real bootstrap can never enter this lazy branch.
const SyntheticResearchApp = lazy(() => import("./research-app").then((module) => ({ default: module.ResearchApp })));

export function V1Entry({ initialView = "research" }: { initialView?: Location["view"] }) {
  const [mode, setMode] = useState<RuntimeMode | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const timeout = setTimeout(() => {
      setMode(null); setFailed(true); controller.abort();
    }, 10_000);
    setMode(null); setFailed(false);
    loadRuntimeMode({ hostname: window.location.hostname, signal: controller.signal })
      .then((value) => { if (!controller.signal.aborted) setMode(value); })
      .catch(() => { if (!controller.signal.aborted) setFailed(true); })
      .finally(() => clearTimeout(timeout));
    return () => { clearTimeout(timeout); controller.abort(); };
  }, [attempt]);
  if (failed) return <main id="main-content" className="runtime-entry-state" role="alert">
    <h1>OCEAN Platform</h1><p>V1 runtime configuration is unavailable. / V1ランタイム設定を利用できません。</p>
    <button className="button primary" onClick={() => setAttempt((value) => value + 1)}>Retry / 再試行</button>
  </main>;
  if (mode === "service") return <RuntimeApp initialDestination={initialView} />;
  if (mode === "synthetic-preview") return <Suspense fallback={<EntryLoading />}><SyntheticResearchApp initialView={initialView} /></Suspense>;
  return <EntryLoading />;
}

function EntryLoading() {
  return <main id="main-content" className="runtime-entry-state" role="status" aria-live="polite"><h1>OCEAN Platform</h1><p>Loading runtime… / ランタイムを読み込んでいます…</p></main>;
}
