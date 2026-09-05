# Model Gateway

NODE-22 provider-neutral model execution boundary for LUMI.

Callers express capabilities through `ModelRequest`; they do not import provider SDKs or receive provider-native response objects. Routing, budget, health, retry/fallback safety, NODE-20 paid-side-effect guarding, provider adapters, normalized usage/cost, streaming, and async status live behind this service.

`MockProvider` is the deterministic CI provider. `OpenAIResponsesAdapter` is the first real HTTP adapter and currently exposes reasoning + structured output only.

See `docs/runtime/MODEL-GATEWAY-V1.md` for the frozen runtime contract.
