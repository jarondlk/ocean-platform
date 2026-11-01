import { redirect } from "next/navigation";
import { auth, signOut } from "../lib/auth";
import { HostRuntime } from "./host-runtime";
import type { ShellDestination } from "../../src/runtime";

export async function HostPage({ destination = "research" }: { destination?: ShellDestination }) {
  const session = await auth();
  if (!session) redirect("/login");
  return <>
    <div style={{ display: "flex", justifyContent: "flex-end", padding: "6px 18px", borderBottom: "1px solid #d7e5ed" }}>
      <form action={async () => { "use server"; await signOut({ redirectTo: "/login" }); }}>
        <button type="submit" className="button secondary">Sign out / ログアウト</button>
      </form>
    </div>
    <HostRuntime destination={destination} />
  </>;
}
