import Link from "next/link";

export default function NotFound() {
  return (
    <main id="main-content" className="system-page" tabIndex={-1}>
      <section className="system-card">
        <p className="eyebrow">404</p>
        <h1>This workspace route doesn’t exist.</h1>
        <p>Return to the LUMI home surface and continue from a known product route.</p>
        <Link className="primary-button" href="/">
          Return home
        </Link>
      </section>
    </main>
  );
}
