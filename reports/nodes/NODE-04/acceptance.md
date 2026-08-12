# NODE-04 Acceptance Report

> Status: **VALIDATING**  
> Node: **NODE-04 — CI Foundation**  
> Implementation Branch: `node-04-ci-foundation`  
> Required Checks: `frontend`, `python`, `contracts`, `integration`, `secret-scan`

## Required evidence

NODE-04 is not COMPLETE until repository evidence proves all of the following:

- A pull request automatically starts the core CI and secret scan workflows.
- `frontend` proves frozen pnpm install, formatting, lint, typecheck, tests, and production build.
- `python` proves frozen uv install, Ruff format/lint, Pyright, and pytest.
- `contracts` proves both lockfiles are reproducible and the current repository/scaffold contract is valid.
- `integration` starts NODE-03 infrastructure and completes the infrastructure smoke test without paid/cloud credentials.
- `secret-scan` blocks a deterministic injected test secret and passes on the clean repository.
- CI caches are tied to lockfile hashes.
- Frontend/Python/integration diagnostics are retained as Actions artifacts where applicable.
- A deliberate bad-code pull request produces a red blocking check and is discarded without merging.
- The target `main` required-check names are documented for repository branch/ruleset configuration.

When the clean PR and deliberate-failure PR have both been observed, this report will record their run IDs, job IDs, final implementation/merge SHA, and any non-blocking repository-capability notes.
