# Sandbox Runtime

NODE-21 isolated execution service for LUMI agent tools.

The local/CI backend uses ephemeral Docker containers behind a provider-neutral `SandboxBackend` contract. Agent-facing adapters never receive host shell, Docker socket, database credentials, or long-lived provider secrets.

See `docs/runtime/SANDBOX-RUNTIME-V1.md` for the frozen security/runtime contract.
