# NODE-02 Acceptance Report

Status: VALIDATING

## Local validation

The execution container cannot resolve npm/PyPI DNS, so dependency installation is intentionally delegated to the repository's GitHub Actions runner. Local validation covers repository structure, manifest parsing, Python syntax and API health using already-installed compatible libraries.

## Required CI evidence

- `pnpm-lock.yaml` generated and committed.
- `uv.lock` generated and committed.
- frozen dependency install succeeds.
- Web/Admin build succeeds.
- API health tests pass.
- Agent runtime dependency imports resolve.
- Media worker imports and health test pass.
- Ruff / Pyright / ESLint / TypeScript / Vitest pass.

The node is not COMPLETE until the above evidence is green.
