# NODE-51 CI Plan

The dedicated workflow `.github/workflows/node-51-auto-repair.yml` runs:

1. contract/static validation;
2. bounded repair tests, NODE-47 compatibility, Ruff and Pyright;
3. PostgreSQL migration and schema/governance assertions.

Hosted execution evidence is required before COMPLETE.
