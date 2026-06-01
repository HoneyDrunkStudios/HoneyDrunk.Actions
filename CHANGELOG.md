# Changelog

## Unreleased

### Changed

- Recorded the ADR-0086 local-worker Grid review rollout and aligned the Grid review caller permissions with the reusable workflow contract.

### Removed

- `job-review-request.yml`: removed the deprecated ADR-0044/OpenClaw compatibility inputs (`openclaw-webhook-url`, `upload-fallback-artifact`, `post-fallback-comment`, `artifact-name`) and the no-op `openclaw-webhook-secret` workflow-call secret. The reusable workflow now exposes only the ADR-0086 local-worker queue contract plus `github-token`; the org secret itself is not removed here.
