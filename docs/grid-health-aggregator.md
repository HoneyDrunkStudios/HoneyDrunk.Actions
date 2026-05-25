# Grid Health Aggregator

`grid-health-report.yml` is the ADR-0012 D6 runtime surface for Grid CI/CD health. It runs daily at `03:30 UTC` and can also be run manually with `workflow_dispatch`.

The workflow reads `HoneyDrunk.Architecture/catalogs/grid-health.json`, requires schema version `>= 1.1`, polls each repo's `tracked_workflows`, and updates the stable `🕸️ Grid Health` issue in `HoneyDrunk.Actions`.

## Classifications

- **Pass** — latest relevant run succeeded inside the staleness window.
- **Fail** — latest run failed, was cancelled, timed out, or needs action.
- **Stale** — the workflow should have produced a recent run but did not.
- **Missing** — the workflow is declared in the catalog but is absent or has never run.

`weekly-*.yml` workflows use an eight-day staleness window. `nightly-*.yml` workflows use a twenty-eight-hour window. `publish.yml` has no staleness window because releases are event-driven.

## How to read the issue

Rows are repos. Columns are tracked workflows. Each non-empty cell links to the latest run when GitHub exposes one. Blank cells mean that workflow is not tracked for that repo.

The `Catalog drift` section lists org repos missing from the Architecture catalog. That is not a workflow failure, but it means the aggregator cannot reason about the repo yet.

## Manual re-run

Open `HoneyDrunk.Actions` → Actions → `Grid Health Report` → **Run workflow**. The run requires `GRID_HEALTH_PAT`; missing or expired tokens fail fast before any issue body is updated.

## Known-broken workflow policy

There is no snooze mechanism today. If a workflow is known broken and intentionally deferred, close the per-repo issue with context; the next aggregator run will reopen it if the state is still red. That friction is intentional until the Grid decides a snooze contract.

## References

- ADR-0012 D6 — Grid Health aggregator.
- HoneyDrunk.Architecture invariant 40 — Grid pipeline health is centrally visible.
