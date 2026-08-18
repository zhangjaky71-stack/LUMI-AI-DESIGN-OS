"use client";

import { useEffect } from "react";

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("LUMI app boundary error", {
      name: error.name,
      message: error.message,
      digest: error.digest,
    });
  }, [error]);

  return (
    <main id="main-content" className="system-page" tabIndex={-1}>
      <section className="system-card" role="alert">
        <p className="eyebrow">Something went wrong</p>
        <h1>We couldn’t load this part of LUMI.</h1>
        <p>
          Retry the request. If the problem continues, keep the reference below for support.
        </p>
        {error.digest ? <code className="error-reference">Ref {error.digest}</code> : null}
        <button className="primary-button" type="button" onClick={reset}>
          Try again
        </button>
      </section>
    </main>
  );
}
