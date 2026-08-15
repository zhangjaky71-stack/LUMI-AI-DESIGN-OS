import { describe, expect, it } from "vitest";
import { LumiApiClient, LumiApiError } from "@/lib/app-shell/api-client";

describe("presigned object upload boundary", () => {
  it("uses credentials omit and does not forward tenant/session headers to object storage", async () => {
    let target = "";
    let captured = new Headers();
    let credentials: RequestCredentials | undefined;
    const transport: typeof fetch = async (input, init) => {
      target = String(input);
      captured = new Headers(init?.headers);
      credentials = init?.credentials;
      return new Response(null, { status: 200 });
    };
    const api = new LumiApiClient({
      transport,
      context: () => ({
        organization_id: "org-sensitive",
        csrf_token: "csrf-sensitive",
      }),
    });

    await api.putPresignedObject(
      "https://objects.example.test/upload?signature=opaque",
      new Blob(["asset"], { type: "image/png" }),
      { content_type: "image/png", headers: { "x-upload-checksum": "abc" } },
    );

    expect(target).toContain("objects.example.test");
    expect(credentials).toBe("omit");
    expect(captured.get("content-type")).toBe("image/png");
    expect(captured.get("x-upload-checksum")).toBe("abc");
    expect(captured.has("x-lumi-organization-id")).toBe(false);
    expect(captured.has("x-csrf-token")).toBe(false);
    expect(captured.has("authorization")).toBe(false);
  });

  it("rejects non-http protocols before transport", async () => {
    let called = false;
    const api = new LumiApiClient({
      transport: async () => {
        called = true;
        return new Response(null, { status: 200 });
      },
    });

    await expect(
      api.putPresignedObject("javascript:alert(1)", new Blob(["x"])),
    ).rejects.toBeInstanceOf(LumiApiError);
    expect(called).toBe(false);
  });
});
