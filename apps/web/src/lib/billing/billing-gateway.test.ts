import { describe, expect, it } from "vitest";
import { DeterministicBillingGateway } from "./billing-gateway";
import { deterministicBillingWorkspace } from "./billing-server";

describe("NODE-63 deterministic billing gateway", () => {
  it("creates hosted checkout without collecting card data", async () => {
    const gateway = new DeterministicBillingGateway(deterministicBillingWorkspace());
    const session = await gateway.createCheckout("pro-v3");
    expect(session.url).toMatch(/^https:\/\/checkout\.mock\.invalid\//);
  });

  it("creates hosted portal and cancel-at-period-end transition", async () => {
    const gateway = new DeterministicBillingGateway(deterministicBillingWorkspace());
    expect((await gateway.createPortal()).url).toContain("portal.mock.invalid");
    expect((await gateway.cancelSubscription()).state).toBe("CANCEL_AT_PERIOD_END");
  });
});
