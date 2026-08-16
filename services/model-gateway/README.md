# model-gateway

NODE-22 implements LUMI's provider-neutral model execution boundary.

Key modules:

- `models.py` — capability/request/result/usage/cost contracts;
- `routing.py` — provider registry and explainable candidate routing;
- `gateway.py` — budget, retry, fallback and normalized async/stream entry points;
- `mock_provider.py` — deterministic no-key CI provider;
- `openai_adapter.py` / `anthropic_adapter.py` — provider HTTP mappings;
- `secrets.py` — Gateway-only secret resolution;
- `serialization.py` — durable NODE-20 replay representation.

Canonical runtime contract: `docs/models/MODEL-GATEWAY-V1.md`.

The package remains dependency-free in the current frozen workspace lock. Provider adapters use
stdlib HTTP so provider SDK classes cannot leak into LUMI domain contracts.
