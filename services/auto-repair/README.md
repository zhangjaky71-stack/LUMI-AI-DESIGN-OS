# LUMI Auto Repair — NODE-51

Bounded, version-safe repair orchestration for exact failed ArtifactVersions.

NODE-51 consumes a NODE-50 `QualityResult`, plans the smallest safe repair, executes candidates on temporary repair branches, re-runs deterministic constraints and quality evaluation, and promotes only an accepted candidate through NODE-42 optimistic concurrency.

NODE-51 never mutates the original ArtifactVersion, never bypasses NODE-39 hard constraints, never writes a second cost ledger, and never overwrites a user-edited main branch. Paid image edits/regeneration reserve budget through NODE-27 before side effects. Structured Design IR fixes delegate to NODE-38. Complex repair recipes remain bounded and auditable through NODE-32 policy/recipe contracts.
