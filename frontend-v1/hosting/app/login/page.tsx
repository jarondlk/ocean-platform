import { signIn } from "../../lib/auth";
import { AuthError } from "next-auth";
import { redirect } from "next/navigation";
export const dynamic = "force-dynamic";
export default function Login() {
  return <main style={{ maxWidth: 440, margin: "14vh auto", padding: 28 }}>

    <h1>Sign in to OCEAN</h1>

    <form action={async () => { "use server";
      try { await signIn("google", { redirectTo: "/" }); }
      catch (error) { if (error instanceof AuthError) redirect("/login"); throw error; }
    }}>
      <button className="button primary" type="submit">Sign in with Google / Googleでログイン</button>
    </form>

  </main>;
}
