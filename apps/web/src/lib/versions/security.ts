const PRIVATE_PROVENANCE_KEYS = new Set([
  "prompt",
  "prompt_ref",
  "raw_prompt",
  "system_prompt",
  "provider_request_id",
  "messages",
  "reasoning",
  "chain_of_thought",
  "scratchpad",
  "tool_output",
  "secret",
  "password",
  "credential",
  "api_key",
  "authorization",
]);

export function assertPublicVersionProvenance(value: unknown): void {
  if (Array.isArray(value)) {
    value.forEach(assertPublicVersionProvenance);
    return;
  }
  if (!value || typeof value !== "object") return;
  for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
    if (PRIVATE_PROVENANCE_KEYS.has(key.toLowerCase())) {
      throw new Error("VERSION_PROVENANCE_PRIVATE_FIELD_FORBIDDEN");
    }
    assertPublicVersionProvenance(child);
  }
}
