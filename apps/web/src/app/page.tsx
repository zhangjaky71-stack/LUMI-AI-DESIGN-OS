import { buildLabel } from "../lib/version";

export default function Home() {
  return (
    <main>
      <p>LUMI AI Design OS</p>
      <h1>Repository bootstrap is running.</h1>
      <p>Architecture V2 · {buildLabel("0.0.0-dev")}</p>
      <p>Next milestone: NODE-03 Local Infrastructure.</p>
    </main>
  );
}
