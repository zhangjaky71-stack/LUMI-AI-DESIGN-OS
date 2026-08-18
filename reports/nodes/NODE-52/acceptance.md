# NODE-52 Acceptance Record

Status: **IMPLEMENTED / VALIDATING / NOT COMPLETE**

## Submitted implementation evidence

- strict TypeScript Next.js App Router package in `apps/web`;
- same-origin browser API client with `/api/*` allowlist;
- controlled server API client with httpOnly-cookie forwarding and ProblemDetails errors;
- validated user/organization/workspace session contract;
- server-side protected shell route group;
- responsive App Shell, primary navigation, tenant top bar and sign-out action;
- Home, Projects handoff, AI Workspace handoff, Settings and Sign-in routes;
- loading, error and not-found boundaries;
- skip-link, focus-visible, `aria-current`, reduced-motion and responsive CSS;
- baseline security headers and same-origin API rewrite;
- static architecture/security validator;
- dedicated TypeScript/production-build workflow;
- explicit production gap ledger.

## Hosted CI evidence

Pending the first NODE-52 workflow execution on the stacked pull request. A queued workflow or a failure before any job step executes is not code-execution evidence.

## Completion blockers

See `reports/nodes/NODE-52/gap-ledger.json`. NODE-52 must remain NOT COMPLETE until real auth/session E2E and Hosted CI produce evidence, and the applicable P1 workspace-lock/browser/CSP gaps are closed or explicitly accepted by their owning gates.
