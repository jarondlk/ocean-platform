import { CredentialsSignin } from "next-auth";
import { LockKeyhole, LogIn, Mail, ShieldCheck } from "lucide-react";
import { redirect } from "next/navigation";

import { signIn } from "@/auth";
import { MOCK_LOGIN_ACCOUNTS } from "@/lib/mock-login";
import { mockLoginEnabled } from "@/lib/security-config";


export const dynamic = "force-dynamic";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; returnTo?: string }>;
}) {
  async function startOrganizationLogin() {
    "use server";
    const params = await searchParams;
    const returnTo =
      params.returnTo &&
      params.returnTo.startsWith("/") &&
      !params.returnTo.startsWith("//")
        ? params.returnTo
        : "/";
    await signIn("oidc", { redirectTo: returnTo });
  }

  async function startMockLogin(formData: FormData) {
    "use server";
    if (!mockLoginEnabled()) {
      throw new Error("Mock login is unavailable");
    }
    const email = formData.get("email");
    const password = formData.get("password");
    if (typeof email !== "string" || typeof password !== "string") {
      redirect("/login?error=invalid");
    }
    const params = await searchParams;
    const returnTo =
      params.returnTo &&
      params.returnTo.startsWith("/") &&
      !params.returnTo.startsWith("//")
        ? params.returnTo
        : "/";
    try {
      await signIn("mock-credentials", {
        email,
        password,
        redirectTo: returnTo,
      });
    } catch (error) {
      if (error instanceof CredentialsSignin) {
        const nextParams = new URLSearchParams({ error: "invalid" });
        if (returnTo !== "/") nextParams.set("returnTo", returnTo);
        redirect(`/login?${nextParams.toString()}`);
      }
      throw error;
    }
  }

  const params = await searchParams;
  const showMockLogin = mockLoginEnabled();
  const loginError = showMockLogin
    ? params.error === "invalid"
      ? "The email or password is incorrect."
      : null
    : params.error
      ? "Sign-in could not be completed. Please try again."
      : null;

  return (
    <section className="login-page">
      <article className="card login-card">
        <header className="login-heading">
          <div className="login-mark" aria-hidden="true">
            <ShieldCheck size={21} />
          </div>
          <div>
            <p className="eyebrow">Onagawa Source Chat</p>
            <h2>Welcome back</h2>
          </div>
        </header>
        <p className="login-intro">
          {showMockLogin
            ? "Use a local mock account to test this research environment."
            : "Continue to secure sign-in with your verified account."}
        </p>

        {loginError ? (
          <p className="login-error" role="alert">
            {loginError}
          </p>
        ) : null}

        {showMockLogin ? (
          <section
            className="mock-login-panel"
            aria-label="Development mock login"
          >
            <div className="mock-login-heading">
              <div>
                <p className="eyebrow">Development access</p>
                <h3>Email and password</h3>
              </div>
              <span className="status-pill">Local only</span>
            </div>
            <form action={startMockLogin} className="mock-login-form">
              <label>
                <span>Email address</span>
                <span className="field-with-icon">
                  <Mail size={15} aria-hidden="true" />
                  <input
                    autoComplete="username"
                    className="field"
                    maxLength={320}
                    name="email"
                    placeholder="name@example.org"
                    required
                    type="email"
                  />
                </span>
              </label>
              <label>
                <span>Password</span>
                <span className="field-with-icon">
                  <LockKeyhole size={15} aria-hidden="true" />
                  <input
                    autoComplete="current-password"
                    className="field"
                    maxLength={256}
                    minLength={12}
                    name="password"
                    required
                    type="password"
                  />
                </span>
              </label>
              <button className="button login-button" type="submit">
                <LogIn size={16} aria-hidden="true" />
                Sign in
              </button>
            </form>
            <div className="mock-account-list">
              <p>Available mock accounts</p>
              {MOCK_LOGIN_ACCOUNTS.map((account) => (
                <div key={account.email}>
                  <span>{account.email}</span>
                  <span className="status-pill">{account.role}</span>
                </div>
              ))}
            </div>
            <p className="mock-login-warning">
              These accounts are stored only in this local test database so
              role, suspension, audit, chat, and feedback behavior can be
              exercised safely.
            </p>
          </section>
        ) : (
          <>
            <form action={startOrganizationLogin}>
              <button className="button login-button" type="submit">
                <ShieldCheck size={16} aria-hidden="true" />
                Sign in
              </button>
            </form>
            <p className="login-support">
              Access is invitation-only. Contact an administrator if your
              verified account is not recognized.
            </p>
          </>
        )}
      </article>
    </section>
  );
}
