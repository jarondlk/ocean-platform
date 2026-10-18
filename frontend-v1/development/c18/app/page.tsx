"use client";

/** Explicit, separately launched loopback development entry. Never a v1 production route. */
import { useMemo, useState } from "react";
import { RuntimeApp } from "../../../src/runtime-app";
import { createC18RunFixture } from "../run-fixture";

export default function DevelopmentResearchPage() {
  const fixture = useMemo(() => createC18RunFixture(), []);
  const [scenario, setScenario] = useState("completed");
  return <><aside style={{ padding: 10, borderBottom: "2px solid #84602d", background: "#fff8e7", color: "#563e14", fontSize: 12 }} aria-label="Development controls"><strong>Local C18 harness · synthetic TEST accounts/data/execution only</strong><label style={{ marginLeft: 14 }}>Next synthetic outcome <select value={scenario} onChange={event => { const next = event.target.value as "completed" | "partial" | "failed" | "clarification" | "running"; setScenario(next); fixture.setScenario(next); }}>{["completed", "partial", "failed", "clarification", "running"].map(value => <option key={value}>{value}</option>)}</select></label></aside><RuntimeApp researchRunTransport={fixture} /></>;
}
