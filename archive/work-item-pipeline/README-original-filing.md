# Historical filing documentation

Retired 2026-10-02. Kept as historical evidence, not current operating instructions.

## 📬 Work Item Filing

`file-work-items.yml` is a reusable workflow that reads work items from `HoneyDrunk.Architecture/generated/work-items/active/`, files them as GitHub Issues in their target repos, adds each one to **The Hive** (GitHub Project v2 #4), mirrors custom fields inline, and links declared `dependencies` across issues as `Blocked by` comments.

### Behavior

- Idempotent: `generated/work-items/filed-work-items.json` in the Architecture repo records which work items have been filed. Re-running skips any work item already in the manifest.
- Labels: frontmatter `labels` plus a synthesized `initiative-<slug>` (derived from the `initiative:` field) are applied at creation so the field mirror picks them up.
- Actor: `actor: Agent` or `actor: Human` in the work item frontmatter is passed to `hive-project-mirror.sh` via `--actor`.
- Dependencies: after all work items are filed, a second pass posts `Blocked by <url>` comments on each dependent issue. Dependencies are matched by basename against the manifest — dependencies not yet filed log a warning and do not fail the run.
- Manifest: `filed-work-items.json` is committed back to the Architecture repo with `[skip ci]` so the caller does not re-trigger.

### Reusable workflow contract

Workflow: `.github/workflows/file-work-items.yml`

Inputs (all optional):

| Input | Default | Purpose |
| --- | --- | --- |
| `architecture-ref` | caller's `github.ref_name` | Branch of the Architecture repo to check out. Must be a branch (not a SHA) so the manifest commit can be pushed back. |
| `work-items-dir` | `generated/work-items/active` | Path under the Architecture repo to scan for `.md` work items. |
| `manifest-path` | `generated/work-items/filed-work-items.json` | Path under the Architecture repo where the manifest lives. |
| `project-owner` | `HoneyDrunkStudios` | Project v2 owner. |
| `project-number` | `4` | Project v2 number (The Hive). |
| `architecture-repo` | `HoneyDrunkStudios/HoneyDrunk.Architecture` | `owner/name` of the Architecture repo. |
| `actions-ref` | derived from `GITHUB_WORKFLOW_REF` | Ref of `HoneyDrunk.Actions` to check out for scripts/config. |

Secret:

- `hive-field-mirror-token` — must grant `issues:write` on every target repo, `organization projects:write` on `HoneyDrunkStudios`, and `contents:write` on the Architecture repo (the workflow pushes the manifest commit).

### Enable in the Architecture repo

Add `.github/workflows/file-work-items.yml`:

```yaml
name: File Work Items

on:
  push:
    branches: [main]
    paths:
      - 'generated/work-items/active/**/*.md'
  workflow_dispatch: {}

jobs:
  file:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/file-work-items.yml@main
    secrets:
      hive-field-mirror-token: ${{ secrets.HIVE_FIELD_MIRROR_TOKEN }}
```

### Local invocation

`scripts/file-work-items.sh` can run outside CI for dry-testing or recovery. It expects to run from a checkout of `HoneyDrunk.Actions` (for the mapping file and mirror script) and needs both the Architecture checkout and valid tokens:

```bash
export GH_TOKEN=***                 # issues:write on target repos
export HIVE_FIELD_MIRROR_TOKEN=***  # project + contents writes

./scripts/file-work-items.sh \
  --work-items-dir /path/to/HoneyDrunk.Architecture/generated/work-items/active \
  --manifest   /path/to/HoneyDrunk.Architecture/generated/work-items/filed-work-items.json
```

Flags:

- `--skip-link-deps` — file work items but skip the `Blocked by` comment pass.
- `--project-owner`, `--project-number` — override The Hive target.
- `--architecture-repo` — override the `owner/name` embedded in issue body headers.
- `--mapping-file` — override the `repo-to-node.yml` path used by the field mirror.

