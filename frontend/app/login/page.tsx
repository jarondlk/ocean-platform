import { LogIn } from "lucide-react";

import { signIn } from "@/auth";


export default function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; returnTo?: string }>;
}) {
  async function startLogin() {
    "use server";
    const params = await searchParams;
    const returnTo =
      params.returnTo && params.returnTo.startsWith("/")
        ? params.returnTo
        : "/";
    await signIn("oidc", { redirectTo: returnTo });
  }

  return (
    <section className="login-page">
      <article className="card login-card">
        <p className="eyebrow">Invite-only access</p>
        <h2>Sign in to Onagawa RAG</h2>
        <p className="empty-state">
          Use the verified organization account matching your invitation.
        </p>
        <form action={startLogin}>
          <button className="button login-button" type="submit">
            <LogIn size={16} aria-hidden="true" />
            Continue with {process.env.OIDC_PROVIDER_NAME || "organization account"}
          </button>
        </form>
      </article>
    </section>
  );
}
