# LUMI Image Edit

NODE-47 bounded context for structural-first and pixel-local image editing.

The service does not call provider SDKs directly. Structural edits are delegated to the Design IR/Constraint boundary; generative edits route through NODE-22 Model Gateway. Source/mask/protected-region provenance and Artifact lineage are immutable audit evidence.
