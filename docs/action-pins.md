# Action Pin Inventory

This inventory tracks third-party GitHub Action pins used by `HoneyDrunk.Actions` workflows and composite actions. It implements ADR-0012 D10: action runtime/deprecation state lives in one reviewable document instead of being rediscovered from workflow logs.

Any PR that adds, removes, or changes a `uses:` pin updates this file in the same PR. Stale entries are a review observation because they hide deprecation work until CI starts warning or failing.

## Inventory

| Action | Current pin | Deprecation deadline | Status | Successor | Notes |
|---|---|---|---|---|---|
| actions/cache | v4 | 2026-09-16 | Deprecated-with-deadline | actions/cache@v5 | Pinned action runs on Node 20; replace before GitHub removes Node 20 action runtime. |
| actions/checkout | v4 | 2026-09-16 | Deprecated-with-deadline | actions/checkout@v5 | Pinned action runs on Node 20; replace before GitHub removes Node 20 action runtime. |
| actions/create-github-app-token | v1 | unknown | Current | none | none |
| actions/download-artifact | v4 | 2026-09-16 | Deprecated-with-deadline | actions/download-artifact@v5 | Pinned action runs on Node 20; replace before GitHub removes Node 20 action runtime. |
| actions/setup-dotnet | v4 | 2026-09-16 | Deprecated-with-deadline | actions/setup-dotnet@v5 | Pinned action runs on Node 20; replace before GitHub removes Node 20 action runtime. |
| actions/setup-node | v4 | 2026-09-16 | Deprecated-with-deadline | actions/setup-node@v5 | Pinned action runs on Node 20; replace before GitHub removes Node 20 action runtime. |
| actions/upload-artifact | v4 | 2026-09-16 | Deprecated-with-deadline | actions/upload-artifact@v5 | Pinned action runs on Node 20; replace before GitHub removes Node 20 action runtime. |
| anthropics/claude-code-action | v1 | unknown | Current | none | none |
| azure/functions-action | v1 | unknown | Current | none | none |
| azure/functions-action | v2 | unknown | Current | none | none |
| azure/login | v2 | unknown | Current | none | none |
| azure/webapps-deploy | v3 | unknown | Current | none | none |
| docker/login-action | v3 | unknown | Current | none | none |
| docker/setup-buildx-action | v3 | unknown | Current | none | none |
| EnricoMi/publish-unit-test-result-action | v2 | unknown | Current | none | none |
| github/codeql-action/analyze | v3 | 2026-09-16 | Deprecated-with-deadline | github/codeql-action/analyze@v4 | Pinned action runs on Node 20; replace before GitHub removes Node 20 action runtime. |
| github/codeql-action/init | v3 | 2026-09-16 | Deprecated-with-deadline | github/codeql-action/init@v4 | Pinned action runs on Node 20; replace before GitHub removes Node 20 action runtime. |
| github/codeql-action/upload-sarif | v3 | 2026-09-16 | Deprecated-with-deadline | github/codeql-action/upload-sarif@v4 | Pinned action runs on Node 20; replace before GitHub removes Node 20 action runtime. |
| peter-evans/create-or-update-comment | v4 | unknown | Current | none | none |
| peter-evans/create-pull-request | v6 | unknown | Current | none | none |
| peter-evans/find-comment | v3 | unknown | Current | none | none |

## Update protocol

- Any PR that adds, removes, or changes an action pin updates this file in the same PR.
- Bumping a `Deprecated-with-deadline` entry to its successor flips `Status` to `Current` and sets the deadline to `none` until a new deprecation is announced.
- Removing an action entirely, such as replacing a marketplace wrapper with direct CLI invocation per invariant 38, deletes the row or records the direct-CLI successor when useful for audit continuity.
- A PR that changes a `uses:` line without updating this inventory is Request Changes unless the changed reference is local (`./...`) or another `HoneyDrunk.Actions` reusable workflow reference.

## Cross-references

- HoneyDrunk.Architecture invariant 38 — reusable workflows invoke tool CLIs directly; this inventory covers the permitted third-party/first-party action surface that remains.
- ADR-0012 D10 — action-pin inventory and update cadence.
- ADR-0012 Gap 5 — future optional workflow can parse `uses:` pins and diff them against this inventory.
