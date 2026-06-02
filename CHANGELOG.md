# Changelog

## Unreleased

### Changed

- Recorded the ADR-0086 local-worker Grid review rollout and aligned the Grid review caller permissions with the reusable workflow contract.
- `pr-core.yml`: the PR Metadata check's `out-of-band` label sync is now best-effort (warns instead of failing the check when the label cannot be applied/removed) and uses `gh issue edit` (the issue-level labels API) so it works under the job's least-privilege `issues: write` permission. Previously the `gh pr edit` path hard-failed with "Resource not accessible by integration" under `pull-requests: read` (a GraphQL mutation failure the best-effort handler downgraded to a warning, so the label was never actually applied). The Authorship + Packet/Out-of-band body fields remain the authoritative, gated source of truth; the label is a cosmetic cue.

### Removed

- `job-review-request.yml`: removed the deprecated ADR-0044/OpenClaw compatibility inputs (`openclaw-webhook-url`, `upload-fallback-artifact`, `post-fallback-comment`, `artifact-name`) and the no-op `openclaw-webhook-secret` workflow-call secret. The reusable workflow now exposes only the ADR-0086 local-worker queue contract plus `github-token`; the org secret itself is not removed here.
