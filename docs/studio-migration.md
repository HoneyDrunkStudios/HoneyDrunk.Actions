# HoneyDrunk.Studio migration

The planning and knowledge repository is being renamed from `HoneyDrunkStudios/HoneyDrunk.Architecture` to `HoneyDrunkStudios/HoneyDrunk.Studio`. This change keeps the GitHub repository identity and the graph/board node ID `honeydrunk-architecture` stable. The new repository name maps to that existing ID; the old key remains a compatibility alias for historical issue data.

## Work-item retirement

The former filing workflow and script are archived under [archive/work-item-pipeline](../archive/work-item-pipeline/README.md). They are removed from executable workflow/script entry points. The generic agent runner no longer injects or mechanically writes packet links into PR bodies; its old `work-item-path` input emits a deprecation warning and has no effect.

Agent-authored PRs still identify authorship and the authorized change. `Request:` or `Approved scope:` is the normal context field. Old `Work Item:` or `Out-of-band reason:` fields remain compatible, but a ticket is not required. Existing authorship, size, test, security and PR-review checks remain active.

The Hive field mirror remains available for labels on existing issues. Grid Health and credential monitoring may still create operational alerts; those are independent of packet-to-ticket filing and remain active.

## Coordinated rollout

1. Confirm the repository rename and matching stable repository identity.
2. Land the Studio archive change with its caller removal and updated Grid Health catalog. Preserve ordinary technical paths such as `catalogs/`, `adrs/` and `repos/`.
3. Land this Actions change so active inventory, health, agent and label-fanout references use Studio. Check the next credential/health runs and a review request on the renamed repository. Do not trigger ticket filing as a smoke test.
4. Land website and current-documentation link updates. Keep historical names in dated evidence where useful.
5. On each installed local worker, update repository-name mappings, review allowlists and remotes to the same renamed repository. The installed `ReviewContext.psm1` pins the old fetch URL and intentionally sets `http.followRedirects=false`, so its context refresh will fail after rename until its URL is updated; keep that security flag unchanged. Keep all existing security limits. A local directory does not have to be renamed if its configured path remains valid.
6. Disable/remove the retired backlog/Hive-sync scheduled jobs from the deployed host and update its installed runner copy. Source archival alone does not change Windows Task Scheduler or deployed configuration. Keep review, docs-sync, audit and unrelated monitoring jobs.

Old GitHub URLs and git remotes normally redirect, but hosted action references do not. Do not reuse the old repository name. GitHub Pages project URLs are also an exception; the repository reported `has_pages: false` at migration preflight. [GitHub rename behavior](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository)

Old Actions tags, SHAs and other branches retain historical filer code. Check any pinned or external callers before declaring the filing system fully retired; do not rewrite shared history or tags as part of this migration. Keep old workflow runs and existing issues for traceability.

## Reversal

Revert the reviewed source changes if necessary. Re-enabling ticket creation or changing the repository name again is a separate deliberate action; do not replay archived work items during recovery.
