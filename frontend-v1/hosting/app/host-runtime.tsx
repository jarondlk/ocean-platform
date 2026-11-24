"use client";
import { useMemo } from "react";
import { RuntimeApp } from "../../src/runtime-app";
import type { ShellDestination } from "../../src/runtime";
import { sessionFetcher } from "../lib/session-fetch";

export function HostRuntime({ destination = "research", signOutAction }: {
  destination?: ShellDestination; signOutAction: () => Promise<void>;
}) {
  const fetcher = useMemo(() => sessionFetcher(), []);
  return <RuntimeApp initialDestination={destination} fetcher={fetcher} signOutAction={signOutAction} />;
}
