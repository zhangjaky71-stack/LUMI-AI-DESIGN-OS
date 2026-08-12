# Main Branch Protection — NODE-05

This document is the repository-setting action required when branch/ruleset administration is not available through the active GitHub connector.

## Target branch

`main`

## Required status checks

Configure the branch/ruleset to require these exact check names before merge:

```text
frontend
python
contracts
integration
secret-scan
eval-smoke
```

`changes` is informational and intentionally not required. `dependency-review` is currently advisory because GitHub native dependency review can require repository security capabilities that are not universally available for private repositories. `CodeQL` is scaffolded and can be enabled for private repositories by setting repository variable `LUMI_ENABLE_CODEQL=1` after CodeQL/security-events support is available.

`eval-smoke` is the NODE-05 offline release gate. It must remain free of paid provider credentials and compares a versioned baseline fixture with the candidate using repository-owned deterministic graders. Live provider evaluation is not a normal PR required check.

## Recommended merge policy

- Require a pull request before merging.
- Require the six checks above to pass.
- Require branches to be up to date before merging once the repository has multiple concurrent contributors.
- Dismiss stale approvals when the head SHA changes if review enforcement is later enabled.
- Block force pushes and branch deletion for `main`.
- Do not allow administrators to silently bypass the required checks during normal development.

## CI ownership rule

Stable required-check names are part of the repository contract. Renaming or deleting one requires updating this document, the relevant Node acceptance evidence, and the branch/ruleset configuration in the same change.

## Secret safety

Do not add provider keys, cloud credentials, production database passwords, authorization headers, or presigned URLs to GitHub Actions logs or artifacts. The blocking `secret-scan` workflow uses Gitleaks and the repository `.gitleaks.toml` policy. Local-only example credentials are allowlisted by path only; the allowlist must not be widened to production configuration paths.

## Benchmark safety

PR benchmark reports may contain synthetic fixtures, aggregate scores, cost estimates, latency estimates, and optional trace IDs. They must not contain production user content, raw provider credentials, authorization headers, or unredacted provider payloads. Recorded provider fixtures introduced later must be explicitly sanitized before commit.
