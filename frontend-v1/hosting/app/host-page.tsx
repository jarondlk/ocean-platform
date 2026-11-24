import { redirect } from "next/navigation";
import { auth, signOut } from "../lib/auth";
import { HostRuntime } from "./host-runtime";
import type { ShellDestination } from "../../src/runtime";

async function signOutAction() {
  "use server";
  await signOut({ redirectTo: "/login" });
}

export async function HostPage({ destination = "research" }: { destination?: ShellDestination }) {
  const session = await auth();
  if (!session) redirect("/login");
  return <HostRuntime destination={destination} signOutAction={signOutAction} />;
}
