# Provider Adapter Mapping V1

## OpenAI

Adapter: `OpenAIResponsesAdapter`  
Endpoint family: Responses API  
Default model alias in NODE-22: `gpt-5.6`  
Capabilities advertised: reasoning, structured output, vision.

Key mapping rules:

- `ModelRequest.inputs` -> Responses input messages/content;
- JSON Schema -> `text.format` structured-output formatter;
- `store=False` is explicit;
- request UUID -> client request trace header;
- provider output/usage -> `NormalizedResult` / `ModelUsage`;
- pricing is injected, never scraped or hard-coded as timeless truth.

Streaming is not enabled by this V1 HTTP adapter. Response retrieval is available as a
reconciliation attempt, but a provider that cannot retrieve a non-stored response causes the
NODE-20 bridge to fail closed as ambiguous rather than generate again.

## Anthropic

Adapter: `AnthropicMessagesAdapter`  
Endpoint family: Messages API  
Pinned V1 model ID: `claude-sonnet-4-20250514`  
Capabilities advertised: reasoning and vision.

Key mapping rules:

- system/developer text -> top-level system content;
- user/assistant text -> Messages entries;
- image reference -> provider image URL content block;
- usage -> normalized token usage;
- API key and version headers stay inside the adapter;
- structured output is not advertised in NODE-22 V1.

## Mock

Adapter: `MockProvider`.

Mock supports every NODE-22 capability and is the CI/reference provider. It is deterministic,
requires no network and can simulate provider error/acceptance states.

## Error acceptance rule

HTTP status and transport failure are normalized separately from provider acceptance.
A category may be fallback-eligible while a paid effect is still barred from fallback because
acceptance is unknown. This is intentional.

## Future adapters

Image/video providers implement the same ProviderAdapter contract and must expose async job
status when the provider is asynchronous. They must not introduce provider-native schemas into
Agent/domain code. NODE-23 owns durable capability/model registration and NODE-27 owns pricing
snapshot truth.
