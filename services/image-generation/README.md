# image-generation

NODE-46 production image-generation orchestration runtime.

The service owns generation specs, reference roles, prompt blocks, variant/budget decisions,
async provider lifecycle, output integrity validation, validation coordination, Artifact candidate
creation, generation provenance and reconciliation hooks.

It does **not** own provider SDK payloads (NODE-22 Model Gateway), binary upload/storage policy
(NODE-18), identity scoring (NODE-44), brand scoring (NODE-43), or image edit/mask protocols
(NODE-47).

Package metadata remains `0.0.0` so the repository's existing frozen `uv.lock` does not need to be
rewritten outside the pinned Python 3.12/uv environment. Runtime API version is exposed separately
as `RUNTIME_VERSION = "1.0.0"`.
