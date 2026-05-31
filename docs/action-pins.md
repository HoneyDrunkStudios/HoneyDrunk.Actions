# Action Pin Inventory

This inventory tracks third-party GitHub Action pins used by `HoneyDrunk.Actions` workflows and composite actions. It implements ADR-0012 D10: action runtime/deprecation state lives in one reviewable document instead of being rediscovered from workflow logs.

Any PR that adds, removes, or changes a `uses:` pin updates this file in the same PR. Stale entries are a review observation because they hide deprecation work until CI starts warning or failing.

## Inventory

| Action | Current pin | Deprecation deadline | Status | Successor | Notes |
|---|---|---|---|---|---|
| actions/cache | v5 | none | Current | none | Bumped to Node 24 successor for ADR-0012 packet 09. |
| actions/checkout | v5 | none | Current | none | Bumped to Node 24 successor for ADR-0012 packet 09. |
| actions/create-github-app-token | v3.2.0 | none | Current | none | Bumped to Node 24 successor for ADR-0012 packet 09 follow-up. |
| actions/download-artifact | v7 | none | Current | none | Bumped to default Node 24 successor for ADR-0012 packet 09. |
| actions/setup-dotnet | v5 | none | Current | none | Bumped to Node 24 successor for ADR-0012 packet 09. |
| actions/setup-java | v5 | none | Current | none | Bumped to Node 24 successor for ADR-0012 packet 09 follow-up. |
| actions/setup-node | v5 | none | Current | none | Bumped to Node 24 successor for ADR-0012 packet 09. |
| actions/setup-python | v5 | none | Current | none | Pins Python 3.12 for `job-discord-notify.yml`'s redaction helper and the `discord_notify` unit tests in `actions-ci.yml` (ADR-0084 D9). |
| actions/upload-artifact | v6 | none | Current | none | Bumped to default Node 24 successor for ADR-0012 packet 09. |
| anthropics/claude-code-action | v1 | unknown | Current | none | none |
| azure/functions-action | v1 | none | Current | none | Valid Node 24 action pin; removed invalid v2 inventory entry. |
| azure/login | v3 | none | Current | none | Bumped to Node 24 successor for ADR-0012 packet 09 follow-up. |
| azure/webapps-deploy | v3 | unknown | Current | none | none |
| docker/login-action | v4 | none | Current | none | Bumped to Node 24 successor for ADR-0012 packet 09 follow-up. |
| docker/setup-buildx-action | v4 | none | Current | none | Bumped to Node 24 successor for ADR-0012 packet 09 follow-up. |
| EnricoMi/publish-unit-test-result-action | v2 | unknown | Current | none | none |
| github/codeql-action/analyze | v4 | none | Current | none | Bumped to Node 24 successor for ADR-0012 packet 09. |
| github/codeql-action/init | v4 | none | Current | none | Bumped to Node 24 successor for ADR-0012 packet 09. |
| github/codeql-action/upload-sarif | v4 | none | Current | none | Bumped to Node 24 successor for ADR-0012 packet 09. |
| peter-evans/create-or-update-comment | v5 | none | Current | none | Bumped to Node 24 successor for ADR-0012 packet 09 follow-up. |
| peter-evans/create-pull-request | v8 | none | Current | none | Bumped to Node 24 successor for ADR-0012 packet 09 follow-up. |
| peter-evans/find-comment | v4 | none | Current | none | Bumped to Node 24 successor for ADR-0012 packet 09 follow-up. |
| softprops/action-gh-release | v3 | none | Current | none | Centralized GitHub Release creation lives in `release.yml` instead of consumer repo-local release jobs. |

## Update protocol

- Any PR that adds, removes, or changes an action pin updates this file in the same PR.
- Bumping a `Deprecated-with-deadline` entry to its successor flips `Status` to `Current` and sets the deadline to `none` until a new deprecation is announced.
- Removing an action entirely, such as replacing a marketplace wrapper with direct CLI invocation per invariant 38, deletes the row or records the direct-CLI successor when useful for audit continuity.
- A PR that changes a `uses:` line without updating this inventory is Request Changes unless the changed reference is local (`./...`) or another `HoneyDrunk.Actions` reusable workflow reference.

## Cross-references

- HoneyDrunk.Architecture invariant 38 — reusable workflows invoke tool CLIs directly; this inventory covers the permitted third-party/first-party action surface that remains.
- ADR-0012 D10 — action-pin inventory and update cadence.
- ADR-0012 Gap 5 — future optional workflow can parse `uses:` pins and diff them against this inventory.
