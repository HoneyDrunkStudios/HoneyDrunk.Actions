# Retired work-item pipeline

Retired on 2026-10-02 at the founder's request. This directory preserves source and documentation for historical inspection. It is outside `.github/workflows` and the active `scripts` entry points.

- `.github/workflows/file-work-items.yml`: former reusable packet-to-issue workflow
- `scripts/file-work-items.sh`: former filing, project-field and dependency-linking script
- `.github/workflows/agent-run.yml`: original generic agent runner with mandatory packet-link insertion; the live runner keeps general agent execution without that enforcement
- `README-original-filing.md`: old setup and invocation documentation

These files are historical evidence, not instructions to run. Existing issues, manifests, commit history and old workflow versions are not deleted. Do not recreate tickets from archived packets.

GitHub can still resolve a reusable workflow pinned to an older commit or tag. Current callers must migrate away from the retired filer; archival on `main` does not revoke old refs. See [rollout notes](../../docs/studio-migration.md).
