# D4 Direct-CLI Retrofit Audit

ADR-0012 D4 requires reusable workflows to invoke tool CLIs directly instead of routing through third-party marketplace wrappers when the tool has a stable CLI. This audit records the current `uses:` surface in `HoneyDrunk.Actions` and the retrofit decisions made in the ADR-0012 rollout PR.

## Audit table

| Surface | Previous reference | Classification | ADR-0012 outcome |
|---|---|---|---|
| `.github/workflows/release.yml` container scan | `aquasecurity/trivy-action@0.35.0` | Third-party marketplace wrapper around stable Trivy CLI | Migrated to direct `docker run aquasec/trivy:0.69.3 image ...` invocation. |
| `.github/workflows/release.yml` SBOM generation | `anchore/sbom-action@v0` | Third-party marketplace wrapper around stable Syft CLI | Migrated to direct Syft install + `syft dir:... --output spdx-json=...` invocation. |
| `.github/workflows/actions-ci.yml` actionlint | `docker://rhysd/actionlint:1.7.12` | Docker image ref ambiguity under D4 | Outcome B chosen below; migrated to direct actionlint install + invocation. |

First-party GitHub actions under `actions/*`, `github/codeql-action/*`, and Azure deployment/login actions remain permitted action references. Local composite actions (`./...`) and reusable workflow calls are outside the marketplace-wrapper concern.

## Policy clarification — `docker://` image refs vs `run: docker run`

ADR-0012 D4 forbids third-party marketplace wrappers but was silent on Docker-image refs (`uses: docker://owner/image:tag`). The actionlint step in `actions-ci.yml` surfaced that ambiguity.

**Chosen outcome: Outcome B — `docker://` is forbidden; prefer install-and-invoke or explicit `run: docker run`.** Even though a `docker://` reference has less wrapper drift than a marketplace action, it still hides tool installation behind the GitHub `uses:` mechanism and creates another permitted shape future contributors must reason about. The canonical D4 forms are:

1. install the tool binary in a `run:` step at a pinned version, then invoke it directly; or
2. invoke a pinned tool image explicitly with `run: docker run ...` when containerized execution is the clearer operational shape.

New uses of `docker://` are forbidden in `HoneyDrunk.Actions`. Existing uses are migrated. The actionlint migration preserves the previous flags exactly: `-color -shellcheck=`.

## Conclusion

The three known D4 retrofit findings from ADR-0012 are addressed in this PR. Future wrapper findings should be filed as small D4 retrofit packets and should update `docs/action-pins.md` when they add, remove, or change a third-party `uses:` pin.

## Cross-references

- HoneyDrunk.Architecture invariant 38 — reusable workflows invoke tool CLIs directly.
- ADR-0012 D4 — direct CLI invocation policy.
- ADR-0012 D10 — action-pin inventory.
