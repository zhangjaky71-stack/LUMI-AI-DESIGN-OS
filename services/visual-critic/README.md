# LUMI Visual Critic — NODE-50

Provider-neutral multi-signal quality control plane for exact ArtifactVersions.

The service aggregates deterministic Constraint/Design IR/OCR/QR/Identity/Brand/metadata evidence with an independently calibrated visual grader. Hard gates always outrank weighted scores. The critic produces a structured `QualityResult` and registered repair actions, but it never mutates or approves the source Artifact itself.

Concrete NODE-39/NODE-43/NODE-44/NODE-22/Artifact adapters live in the API layer. Quality results are linked to immutable ArtifactVersions in LUMI DB and do not depend on LangSmith availability.
