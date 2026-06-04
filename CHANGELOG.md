# Changelog

## Unreleased

### Changed

- Recorded the ADR-0086 local-worker Grid review rollout and aligned the Grid review caller permissions with the reusable workflow contract.
- `pr-core.yml`: the PR Metadata check's `out-of-band` label sync is now best-effort (warns instead of failing the check when the label cannot be applied/removed) and uses `gh issue edit` (the issue-level labels API) so it works under the job's least-privilege `issues: write` permission. Previously the `gh pr edit` path hard-failed with "Resource not accessible by integration" under `pull-requests: read` (a GraphQL mutation failure the best-effort handler downgraded to a warning, so the label was never actually applied). The Authorship + Packet/Out-of-band body fields remain the authoritative, gated source of truth; the label is a cosmetic cue.

### Fixed

- `actions/azure/deploy-function`: the post-deploy health check now probes the function app's real `defaultHostName` (resolved via `az resource show --resource-type Microsoft.Web/sites`) instead of the assumed `<name>.azurewebsites.net`. Flex Consumption apps answer only on a regional hostname (`<name>-<hash>.<region>-01.azurewebsites.net`), so the bare form returned HTTP 000 and failed the health check even when the deploy itself succeeded. `az functionapp show` is deliberately avoided here — it returns null for `defaultHostName`/`state`/`hostNames` on Flex Consumption apps (a CLI quirk); `az resource show` reads the property straight from ARM and is correct for both Flex and classic plans. Falls back to the constructed form (with a warning) when the lookup is unavailable. Applies to both the production-URL and post-swap-URL resolution.

### Removed

- `job-review-request.yml`: removed the deprecated ADR-0044/OpenClaw compatibility inputs (`openclaw-webhook-url`, `upload-fallback-artifact`, `post-fallback-comment`, `artifact-name`) and the no-op `openclaw-webhook-secret` workflow-call secret. The reusable workflow now exposes only the ADR-0086 local-worker queue contract plus `github-token`; the org secret itself is not removed here.
