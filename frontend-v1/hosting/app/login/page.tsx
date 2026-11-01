import { signIn } from "../../lib/auth";
import { AuthError } from "next-auth";
import { redirect } from "next/navigation";
export const dynamic = "force-dynamic";
export default function Login() {
  return <main style={{ maxWidth: 440, margin: "14vh auto", padding: 28 }}>
    <p style={{ color: "#2185ad", letterSpacing: ".16em" }}>OCEAN</p>
    <h1>Sign in to OCEAN</h1>
    <p>Use your invited beta account. / 招待されたベータアカウントでログインしてください。</p>
    <form action={async () => { "use server";
      try { await signIn("google", { redirectTo: "/" }); }
      catch (error) { if (error instanceof AuthError) redirect("/login"); throw error; }
    }}>
      <button className="button primary" type="submit">Sign in with Google / Googleでログイン</button>
    </form>
    <p className="muted small">Access is checked with the independent OCEAN service. If sign-in is unavailable, contact the beta operator.</p>
  </main>;
}
