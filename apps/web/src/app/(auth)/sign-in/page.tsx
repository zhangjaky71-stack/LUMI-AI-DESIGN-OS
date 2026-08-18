import { redirect } from "next/navigation";

import { getAppSession } from "@/lib/auth/session";
import { getWebRuntimeConfig } from "@/lib/config/env";

export default async function SignInPage() {
  const session = await getAppSession();
  if (session) redirect("/");
  const { signInPath } = getWebRuntimeConfig();

  return (
    <main id="main-content" className="auth-page" tabIndex={-1}>
      <section className="auth-card" aria-labelledby="sign-in-title">
        <a className="auth-brand" href="/" aria-label="LUMI home">
          <span className="brand-mark" aria-hidden="true">L</span>
          <span>
            <strong>LUMI</strong>
            <small>Design OS</small>
          </span>
        </a>
        <div className="auth-copy">
          <p className="eyebrow">Welcome back</p>
          <h1 id="sign-in-title">Enter your design workspace.</h1>
          <p>
            Authentication is handled by the configured LUMI identity service.
            Your browser session stays in secure cookies rather than local storage.
          </p>
        </div>
        <a className="primary-button auth-action" href={signInPath}>
          Continue to sign in
        </a>
        <p className="auth-footnote">
          Access is scoped to your organization and workspace after authentication.
        </p>
      </section>
    </main>
  );
}
