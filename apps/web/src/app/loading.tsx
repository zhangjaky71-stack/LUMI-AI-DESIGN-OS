export default function Loading() {
  return (
    <main id="main-content" className="system-page" aria-busy="true" tabIndex={-1}>
      <section className="loading-card" aria-label="Loading LUMI workspace">
        <span className="loading-bar wide" />
        <span className="loading-bar medium" />
        <span className="loading-panel" />
      </section>
    </main>
  );
}
