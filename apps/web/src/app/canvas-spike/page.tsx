import type { Metadata } from "next";

import CanvasSpikeClient from "./CanvasSpikeClient";

export const metadata: Metadata = {
  title: "LUMI Canvas Technology Spike",
  description: "NODE-08 PixiJS infinite canvas feasibility and performance spike.",
};

export default function CanvasSpikePage() {
  return <CanvasSpikeClient />;
}
