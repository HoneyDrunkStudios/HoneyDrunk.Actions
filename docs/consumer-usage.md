# Consumer Usage Guide

Node/TypeScript/RN-web consumers: use the [Node quality contract](node-quality.md)
for the extended `job-node-workspace.yml`, fast PR and manual/release gates,
dependency audit reuse, and the proposed native device E2E boundary.

This document provides sample workflows for consuming repos to adopt the HoneyDrunk.Actions workflow families.

> Authoritative per ADR-0012 D9 (Decision: caller-workflow scaffolding is documented here). The canonical baselines below are the source of truth for invariant 39 (caller-workflow `permissions:` superset rule).

## Script coverage

Mixed-language consumers of `job-sonarcloud.yml` can pass `generic-coverage-report-path: TestResults/script-coverage.xml` for measured [Sonar generic coverage](https://docs.sonarsource.com/sonarqube-cloud/analyzing-source-code/test-coverage/generic-test-data). Collect execution coverage with the language's test tool, convert its real line/branch counts, and include that XML in the artifact selected by `coverage-artifact-name` alongside the existing OpenCover files. The artifact downloads under the caller's `TestResults` directory. An explicitly requested missing report fails before upload; no report is synthesized, no tests are excluded, and server/new-code gates remain unchanged. For push-to-main, the caller must also produce its script report before analysis; the built-in fallback runs only .NET tests.

## Caller permissions — the load-bearing rule

Every caller workflow that consumes a reusable workflow from `HoneyDrunk.Actions` must declare a top-level `permissions:` block. Under `workflow_call`, the callee's `permissions:` block is purely documentary — the effective job token permissions are determined by the **caller**. A caller that omits `permissions:` inherits the repository's default token scope (`contents: read`, all writes `none` in the default GitHub Actions configuration), and any reusable workflow that requests a `write` scope fails at workflow-load time with a validation error, before a single step runs.

This rule is invariant 39 in `HoneyDrunk.Studio/constitution/invariants.md` and is governed by ADR-0012 D5.

**Validation failure is silent until the next scheduled run.** If you add a new caller without `permissions:`, your PR may merge cleanly (the workflow-load check runs at trigger time, not at merge time). The grid-health aggregator (`grid-health-report.yml`) classifies the workflow as **Stale** when its scheduled trigger fails to produce a run, surfacing the bug within ~24 hours. The review agent's Request Changes rule (per `.claude/agents/review.md`) is the earlier safety net.

The canonical permissions baselines below are minimum sets. Granting more than required is legal but discouraged. Granting less is broken at workflow-load time.

| Reusable workflow | Minimum caller `permissions:` |
|---|---|
| `pr-core.yml` | `contents: read`, `pull-requests: write`, `checks: write`, `security-events: write`, `issues: write` |
| `pr-sdk.yml` | `contents: read`, `pull-requests: write`, `checks: write`, `security-events: write`, `issues: write` |
| `job-node-workspace.yml` | `contents: read` |
| `job-rust-workspace.yml` | `contents: read` |
| `job-node-dependency-report.yml` | `contents: read` |
| `job-rust-dependency-report.yml` | `contents: read` |
| `job-node-security-audit.yml` | `contents: read` |
| `job-rust-security-audit.yml` | `contents: read` |
| `job-discord-notify.yml` | none required (`permissions: {}` callee; any caller block is a superset) |
| `release.yml` | `contents: write`, `packages: write`, `id-token: write`, `security-events: write` |
| `job-solution-preflight.yml` | `contents: read` |
| `job-dotnet-publish-artifact.yml` | `contents: read` |
| `job-deploy-container.yml` | `contents: read`, `id-token: write` |
| `job-deploy-container-app.yml` | `contents: read`, `id-token: write` |
| `job-deploy-function.yml` | `contents: read`, `id-token: write` |
| `nightly-security.yml` | `actions: read`, `contents: read`, `security-events: write`, `issues: write` |
| `nightly-deps.yml` | `contents: write`, `pull-requests: write`, `issues: write` |
| `nightly-accessibility.yml` | `contents: read`, `issues: write` |
| `weekly-governance.yml` | `contents: read`, `issues: write` |
| `job-sonarcloud-quality-gate.yml` | `contents: read` |

For workflows not explicitly listed in ADR-0012 D5, the baseline is derived from the callee workflow's declared top-level and job-level `permissions:` blocks in `.github/workflows/<callee>.yml`.

## Table of Contents

- [Caller permissions — the load-bearing rule](#caller-permissions--the-load-bearing-rule)
- [PR Core Workflow](#pr-core-workflow)
- [Node Workspace Job](#node-workspace-job)
- [Rust Workspace Job](#rust-workspace-job)
- [Terraform validation workflow](#terraform-validation-workflow)
- [Bicep lint compatibility](#bicep-lint-workflow)
- [Bicep deploy compatibility](#deploy-bicep-workflow)
- [SonarQube Cloud Quality Gate](#sonarqube-cloud-quality-gate)
- [PR SDK Workflow](#pr-sdk-workflow)
- [Legacy PR review retirement](#legacy-pr-review-retirement)
- [Discord Operator-Alert Notification](#discord-operator-alert-notification)
- [Release Workflow](#release-workflow)
- [Deploy Container to Azure App Service](#deploy-container-to-azure-app-service)
- [Deploy Azure Container App](#deploy-azure-container-app)
- [Deploy Azure Function App](#deploy-azure-function-app)
- [Nightly Security Workflow](#nightly-security-workflow)
- [Nightly Dependencies Workflow](#nightly-dependencies-workflow)
- [Nightly Accessibility Workflow](#nightly-accessibility-workflow)
- [Weekly Governance Workflow](#weekly-governance-workflow)

---

## PR Core Workflow

**Purpose:** Fast PR validation for most repos. Required check that provides quick feedback.

**When to Use:** All repos that need basic CI validation (build, test, standards).

For a nested .NET solution, pass `project-path` relative to `working-directory`;
static analysis uses that same target for restore and formatting. Set
`fail-on-formatting-issues: true` on `pr-core.yml` to fail on formatting differences.
The default keeps differences advisory, but formatter invocation/workspace errors
always fail. The static-analysis reusable workflow is resolved at the same commit
as PR Core, so a reviewed commit pin covers this fix without changing other jobs'
working directories or coverage paths.

### Minimal Example

```yaml
name: PR Validation

on:
  pull_request:
    branches: [main, develop]

jobs:
  pr-validation:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/pr-core.yml@main
```

## Node Workspace Job

**Purpose:** Fast PR validation for TypeScript/JavaScript repos that own their build, test, and lint scripts.

**When to Use:** React/Vite, Node package, and npm-workspace repos that do not need the .NET-centered `pr-core.yml` pipeline.

### npm Workspace Example

```yaml
name: PR

on:
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  node:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/job-node-workspace.yml@main
    with:
      node-version-file: .nvmrc
      install-command: npm ci
      build-command: npm run build
      test-command: npm test
      lint-command: npm run lint
```

### Permissions

`job-node-workspace.yml` callers need `contents: read` for checkout. The caller owns the trigger and branch rules. Keep check names stable by naming the caller job intentionally, because GitHub branch rules bind to the caller workflow's produced checks, not to this documentation.

## Rust Workspace Job

**Purpose:** Fast PR validation for Cargo workspaces.

**When to Use:** Rust crates and mixed repos that need Cargo build/test/lint lanes.

### Cargo Workspace Example

```yaml
name: PR

on:
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  rust:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/job-rust-workspace.yml@main
    with:
      rust-toolchain: stable
      build-command: cargo build --workspace
      test-command: cargo test --workspace
      clippy-command: cargo clippy --workspace --all-targets -- -D warnings
```

### Permissions

`job-rust-workspace.yml` callers need `contents: read` for checkout. The job installs `rustfmt` and `clippy` through `rustup` and caches Cargo registry/git/target directories with `actions/cache`.

### ADR-0044 Authorship and PR-Size Discipline

`pr-core.yml` requires every PR body to contain exactly one authorship declaration:

```text
Authorship: human
```

Allowed classes are `human`, `agent-codex`, `agent-copilot`, `agent-claude-code`, and `mixed`. The `authorship-check` job fails when the line is absent or unparseable; it does not silently assume `human`.

For non-`human` PRs, `pr-metadata-check` requires meaningful request context before size review:

- Use `Request:` or `Approved scope:` to describe the authorized change. A work item is not required, and a direct request is not classified as out of band.
- Historical `Work Item:` and `Out-of-band reason:` fields remain accepted for old callers. Those two legacy fields are mutually exclusive, with the existing best-effort label sync.
- Empty or placeholder context still fails. Authorship, review, tests and size checks remain in force.


For non-`human` PRs, `pr-size-check` counts non-test changed lines. It excludes common test paths and any configured `.honeydrunk-review.yaml` `skip_paths`; missing config or missing `skip_paths` is treated as an empty list, not an error.

Phase 2 posture is warnings-only:

- `<= 400` non-test changed lines: no action.
- `> 400` and `<= 800`: applies `large-pr` and requests a `Size justification:` block if missing.
- `> 800`: applies `large-pr` and comments requesting a split or `refine` pass.

The size job does not fail PRs in Phase 2. ADR-0044 Phase 3 owns any harder posture.

Consumer repos should add these PR-body placeholders before enabling the check broadly. The safest path is a `.github/pull_request_template.md` in each repo, or an organization-default template from the org `.github` repository:

```markdown
Authorship: human
Request: N/A (describe the direct request or approved scope; no work item required)
Size justification: N/A
```

`large-pr`, `audit-sample`, `out-of-band`, `post-merge-audit-in-progress`, `post-merge-audited`, and `post-merge-audit-findings` are defined in `.github/config/labels.json` and can be seeded with `seed-labels.yml` / `seed-labels-fanout.yml`. The size job also attempts to apply `large-pr` automatically when the threshold is crossed; label seeding keeps that path quiet instead of relying on best-effort creation at review time.

### Coverage Gate and Baseline Ratchet

`pr-core.yml` enforces coverage for repos that contain `.Tests` or `.Canary` projects. Repos without test projects skip the gate visibly with `Coverage gate: skipped (no test projects)`.

The gate evaluates:
- patch coverage for added/changed executable lines, default `patch-coverage-threshold: 75`
- no-regress against `.github/coverage-baseline.json`
- absolute total line coverage floor, default `absolute-coverage-floor: 70`

The baseline file is maintained in each consumer repo as:

```json
{
  "totalLineCoverage": 76.42,
  "commit": "<sha>",
  "measuredAtUtc": "<utc timestamp>"
}
```

Treat `.github/coverage-baseline.json` as bot-maintained. A deliberate coverage regression should edit that file in the same PR so the change is reviewable.

To let the baseline ratchet seed/update after merges, call `coverage-baseline-ratchet.yml` from a separate `push`-to-default-branch job and grant only that job `contents: write` so it can commit the bot-maintained baseline. The `pr-core.yml` PR job should keep `contents: read`. A pull-request-only caller still enforces no-regress when `.github/coverage-baseline.json` already exists, but the baseline will not auto-ratchet after merges; if the file does not exist yet, PRs remain in bootstrap mode until it is seeded.

Optional inputs:

```yaml
with:
  patch-coverage-threshold: 75
  absolute-coverage-floor: 70
```

### SonarQube Cloud Quality Gate

`job-sonarcloud.yml` waits up to 300 seconds for server processing and the
project quality gate. Upload success alone is insufficient: a failed gate,
processing error or timeout fails the scanner job. This does not create or
replace the external `SonarCloud Code Analysis` check; confirm the Sonar
project's GitHub binding and App access when that required check is absent.
Keep inspecting the exact analyzed head's new issues and security hotspots,
because a passing project gate does not imply zero findings.

For SQL Server repositories, set `sonar-tsql: true` on the
`job-sonarcloud.yml` caller. Sonar otherwise assigns `.sql` files to Oracle
PL/SQL. This opt-in assigns `.sql`/`.tsql` to T-SQL and retains
`.plsql`/`.pks`/`.pkb` for PL/SQL; it does not exclude SQL files or suppress
rules. Leave the default `false` for other dialects. Verify the actual analyzer
and indexed files in a consumer run before claiming SQL coverage. See
[Sonar's T-SQL configuration](https://docs.sonarsource.com/sonarqube-cloud/analyzing-source-code/languages/t-sql).

`pr-core.yml` can optionally poll SonarQube Cloud PR new-code metrics after `job-sonarcloud.yml` has uploaded analysis data. This exists because the free SonarQube Cloud "Sonar way" gate cannot be customized to fail on every new issue, so HoneyDrunk enforces ADR-0011 D11 thresholds in Actions while using SonarQube Cloud as the data source.

Default posture is off and warn-only:

- `enable-sonar-quality-gate: false` means existing consumers do not change behavior.
- `sonar-quality-gate-mode: warn` reports breaches in the check and PR summary without failing the PR.
- `sonar-quality-gate-mode: enforce` fails the PR when any configured threshold is exceeded.
- Missing PR measures are reported as a warning and do not hard-fail, matching fork PRs or caller workflows that skipped Sonar analysis. SonarQube Cloud authorization and configuration errors fail because the gate could not evaluate the PR.

Start with a per-repo opt-in like:

```yaml
with:
  enable-sonar-quality-gate: true
  sonar-quality-gate-mode: warn
  sonar-organization: 'honeydrunkstudios'
  sonar-project-key: 'honeydrunkstudios_HoneyDrunk.Vault'
secrets:
  github-token: ${{ secrets.GITHUB_TOKEN }}
  sonar-token: ${{ secrets.SONAR_TOKEN }}
```

Sequencing matters. Current HoneyDrunk consumer workflows usually run the `sonarcloud` job after `pr-core`, so immediate blocking enforcement should call the standalone gate after `sonarcloud`:

```yaml
  sonar-quality-gate:
    name: SonarQube Cloud Quality Gate
    if: github.event_name == 'pull_request' && needs.sonarcloud.result == 'success'
    needs: sonarcloud
    permissions:
      contents: read
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/job-sonarcloud-quality-gate.yml@main
    with:
      sonar-organization: 'honeydrunkstudios'
      sonar-project-key: 'honeydrunkstudios_HoneyDrunk.Vault'
      mode: enforce
    secrets:
      sonar-token: ${{ secrets.SONAR_TOKEN }}
```

Threshold inputs default to zero, meaning no new issues or hotspots are allowed:

```yaml
with:
  sonar-max-new-violations: 0
  sonar-max-new-bugs: 0
  sonar-max-new-vulnerabilities: 0
  sonar-max-new-code-smells: 0
  sonar-max-new-security-hotspots: 0
```

### Full Example with Options

```yaml
name: PR Validation

on:
  pull_request:
    branches: [main, develop]
  push:
    branches: [main]

permissions:
  contents: read  # broader writes are granted per-job (least privilege)

jobs:
  pr-validation:
    if: github.event_name == 'pull_request'
    # security-events: write is scoped here because pr-core's CodeQL step
    # uploads SARIF to GitHub Code Scanning. checks: write and
    # pull-requests: write are scoped here too so additional jobs don't
    # inherit them implicitly.
    permissions:
      contents: read
      checks: write
      issues: write          # lets pr-metadata-check manage out-of-band / pr-size manage large-pr
      pull-requests: write
      security-events: write
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/pr-core.yml@main
    with:
      dotnet-version: '10.0.x'
      configuration: 'Release'
      runs-on: 'ubuntu-latest'
      working-directory: '.'
      project-path: './src/MyProject.sln'
      enable-secret-scan: true
      enable-dependency-scan: true
      dependency-fail-on-severity: 'high'
      enable-codeql: true
      codeql-queries: 'security-and-quality'
      codeql-fail-on-severity: 'note'   # any finding blocks; set 'warning' or 'error' to loosen
      enable-sonar-quality-gate: false
      enable-accessibility-check: false
      patch-coverage-threshold: 75
      absolute-coverage-floor: 70
      post-pr-summary: true
      actions-ref: 'main'
    secrets:
      github-token: ${{ secrets.GITHUB_TOKEN }}
      # Required only when enable-sonar-quality-gate is true.
      # sonar-token: ${{ secrets.SONAR_TOKEN }}

  coverage-baseline-ratchet:
    if: github.event_name == 'push'
    permissions:
      contents: write
      checks: write
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/coverage-baseline-ratchet.yml@main
    with:
      dotnet-version: '10.0.x'
      configuration: 'Release'
      runs-on: 'ubuntu-latest'
      working-directory: '.'
      project-path: './src/MyProject.sln'
      actions-ref: 'main'
    secrets:
      github-token: ${{ secrets.GITHUB_TOKEN }}
```

Dependency scan now fails closed when it cannot resolve a solution or package project. Set `project-path` explicitly for repos with nested solutions, multiple solution files, or non-standard layouts so `pr-core.yml` scans the intended graph. Solution targets may live under a subdirectory; package project paths listed by the solution are normalized relative to that solution file before each project is scanned, SQL database projects are ignored because they do not produce the `dotnet list package` JSON contract, and coverage validation resolves `.` / `..` path segments before comparing scan output. This stricter behavior can newly red consumer repos that previously passed with a whole-solution scan or implicit working-directory scan; roll it out under a reviewed Actions ref/tag and validate at least one representative nested or multi-solution consumer before promoting the change broadly through `actions-ref: main`. Per-project scanning can increase CI minutes for larger solutions because each package project is scanned independently. The reusable job checks out `HoneyDrunk.Actions` at `.github/actions-repo` using `actions-ref` (`main` by default), honors explicit `actions-ref` overrides for reviewed branch/tag/SHA rollouts, logs the selected ref and scan target, and verifies the checked-in helper script exists before invoking it. The job requires a Linux-compatible Bash runner with `python3`; the default `ubuntu-latest` runner satisfies both requirements.

### Web App with Accessibility Check

```yaml
name: PR Validation

on:
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  pr-validation:
    permissions:
      contents: read
      checks: write
      issues: write          # lets pr-metadata-check manage out-of-band / pr-size manage large-pr
      pull-requests: write
      security-events: write  # CodeQL SARIF upload
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/pr-core.yml@main
    with:
      enable-accessibility-check: true
      accessibility-url: 'http://localhost:5000'
    secrets:
      github-token: ${{ secrets.GITHUB_TOKEN }}
```

---

### Permissions

`pr-core.yml` callers need an explicit top-level or job-level permissions block that grants `contents: read`, `checks: write`, `pull-requests: write`, `security-events: write`, and `issues: write`. `issues: write` is part of the baseline because PR metadata/size checks maintain labels and comments. Under `workflow_call`, the callee declaration is documentary, so missing or under-granted caller permissions fail at workflow-load time and later surface through grid-health as Stale. Extra scopes are allowed only when another job in the same workflow needs them; prefer least privilege.


## Terraform validation workflow

Use [`job-terraform-validate.yml`](../.github/workflows/job-terraform-validate.yml)
for the current [Infrastructure source](https://github.com/HoneyDrunkStudios/HoneyDrunk.Infrastructure). The
[full contract](terraform-validation.md) defines the root manifest, module layout,
provider lock, mocked test files and caller ownership tests. It needs only
`contents: read`; no Azure login or state backend is initialized.

Copy the current reviewed immutable pin from
[Infrastructure's caller](https://github.com/HoneyDrunkStudios/HoneyDrunk.Infrastructure/blob/main/.github/workflows/pr.yml), using
the same SHA in `uses` and `actions-ref`. Example at the merged migration's pin:

```yaml
permissions:
  contents: read
jobs:
  terraform:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/job-terraform-validate.yml@6d3a24de668ea46165ca791e871ea00910d08240
    with:
      actions-ref: 6d3a24de668ea46165ca791e871ea00910d08240
```

`working-directory` defaults to `.` and may select a relative directory within
the caller checkout. The pinned job checks formatting, backend-disabled/read-only
lock initialization, schema validation, counted mocked plan tests and the caller's
Python ownership checks. Keep secret scanning and existing required checks too.
Infrastructure's required `Bicep Lint / Bicep Lint` name is a fail-closed aggregate
of Terraform and secret checks; it is not an instruction to restore Bicep.

## Bicep Lint Workflow

**Historical compatibility only.** [`job-bicep-lint.yml`](../.github/workflows/job-bicep-lint.yml)
still exists for separately managed legacy callers, but Infrastructure no longer
uses it. The former `.bicep`/`.bicepparam` consumer example is superseded by
[Terraform validation](#terraform-validation-workflow). Inspect the workflow source
for the retained legacy contract; do not add it to new Infrastructure callers.

## Deploy Bicep Workflow

**Historical compatibility only.** [`job-deploy-bicep.yml`](../.github/workflows/job-deploy-bicep.yml)
remains source for legacy callers, not a current Infrastructure deploy path.
Infrastructure removed its Bicep dispatcher and templates. The old
`nodes/identity/main.bicep` and parameter-file examples are obsolete.

There is no replacement Terraform apply/import workflow to invoke. Follow the
[migration/adoption runbook](https://github.com/HoneyDrunkStudios/HoneyDrunk.Infrastructure/blob/main/docs/terraform-migration.md) and
[state/authentication design](https://github.com/HoneyDrunkStudios/HoneyDrunk.Infrastructure/blob/main/docs/terraform-state.md) for
separately approved operational work. Never convert the source-validation job
into a live plan/apply mode or print state/saved plans into PR logs. Runtime image
delivery is a different concern; see [App Service development](app-service-development.md).

## Legacy PR review retirement

The founder authorized full Grid Review retirement on October 10, 2026.
`job-review-request.yml`, its PR-event callers, and `.honeydrunk-review.yaml`
are retired. Do not add a caller or recreate the six former review labels.
Tests, Sonar/security checks, PR metadata/authorship/size checks and manual
review remain required. Greptile setup and required-check changes are separate
approvals; retirement does not claim Greptile is installed or authorize merge.

Post-merge audit is retained. Its `audit-sample` queue now has distinct
`post-merge-audit-in-progress`, `post-merge-audited`, and
`post-merge-audit-findings` state labels. Install the matching reviewed audit
configuration before removing the three shared legacy state labels. Merge
this central catalog and seed-filter change before live label cleanup. Both
seeding entry points filter the six retired names even from an older catalog
source ref; unrelated labels continue to be seeded.


## Discord Operator-Alert Notification

**Purpose:** Post one operator-alert to a Discord channel via the canonical seam per [ADR-0084](https://github.com/HoneyDrunkStudios/HoneyDrunk.Studio/blob/main/adrs/ADR-0084-discord-operator-alerts-surface.md) D9. Every GitHub-Actions emitter routes through `job-discord-notify.yml`; ad-hoc `curl` to a Discord webhook URL elsewhere is forbidden (ADR-0084 D11).

**When to Use:** Any workflow that needs to surface an operator-actionable event (CI failure on `main`, release/NuGet event, scheduled-workflow failure, credential-rotation escalation, agent/hive/security signal). Pick the channel + severity from the ADR-0084 D6 routing table.

The callee validates the `channel`/`severity` enums, runs a fail-closed redaction pre-check (no secret values, PII, or credentials reach a channel — ADR-0084 D8 / Invariant 8), enforces Discord's embed limits, and POSTs the formatted embed to the channel's `DISCORD_WEBHOOK_*` org secret.

### Minimal Caller

```yaml
jobs:
  notify:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/job-discord-notify.yml@v1
    with:
      channel: ops-alerts          # ops-alerts | security-alerts | agent-activity | hive-activity | release | announcements | audit-sensitive
      severity: high               # info | medium | high | critical
      title: "❌ ${{ github.repository }} / ${{ github.workflow }} failed on main"
      link: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
    secrets: inherit
```

### With body + structured metadata

```yaml
jobs:
  notify:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/job-discord-notify.yml@v1
    with:
      channel: release
      severity: info
      title: "📦 HoneyDrunk.Kernel 1.4.0 published"
      body: "Published to nuget.org from ${{ github.sha }}"
      metadata: '{"package":"HoneyDrunk.Kernel","version":"1.4.0"}'   # JSON OBJECT only; rendered as embed fields
    secrets: inherit
```

### Inputs

| Input | Required | Notes |
|---|---|---|
| `channel` | yes | One of the seven ADR-0084 D2 channels. |
| `severity` | yes | `info` / `medium` / `high` / `critical` — selects embed color + emoji. |
| `title` | yes | One-line summary (truncated to 200 chars). |
| `body` | no | Longer text → embed description (truncated to 4000 chars). |
| `link` | no | URL the alert points at; makes the title clickable. Scanned by the redaction pre-check. |
| `metadata` | no | A JSON **object** rendered as embed fields. Arrays/strings/numbers are rejected. |

### Permissions

`job-discord-notify.yml` declares `permissions: {}` — the Discord POST is HTTP-only and needs no GitHub API scope, so **any** caller `permissions:` block is a trivially-satisfied superset (Invariant 39). Pass `secrets: inherit` so the seven `DISCORD_WEBHOOK_*` org secrets resolve. `DISCORD_WEBHOOK_AUDIT_SENSITIVE` is restricted to Architecture / Vault / Vault.Rotation / Audit (ADR-0084 D4); a `channel: audit-sensitive` call from any other repo fails at secret resolution, which is correct.

---

## PR SDK Workflow

**Purpose:** PR validation for SDK/library repos with public APIs.

**When to Use:** NuGet libraries, SDKs, shared libraries with public API surfaces.

### Minimal Example

```yaml
name: PR SDK Validation

on:
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  pr-sdk-validation:
    permissions:
      contents: read
      checks: write
      pull-requests: write
      security-events: write  # CodeQL SARIF upload
      issues: write           # PR summary comments
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/pr-sdk.yml@main
    secrets:
      github-token: ${{ secrets.GITHUB_TOKEN }}
```

### Full Example with Coverage and API Baseline

```yaml
name: PR SDK Validation

on:
  pull_request:
    branches: [main, develop]

permissions:
  contents: read

jobs:
  pr-sdk-validation:
    permissions:
      contents: read
      checks: write
      pull-requests: write
      security-events: write  # CodeQL SARIF upload
      issues: write           # PR summary comments
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/pr-sdk.yml@main
    with:
      dotnet-version: '10.0.x'
      configuration: 'Release'
      project-path: './src/MyLibrary/MyLibrary.csproj'
      api-compat-baseline: './api-baseline.txt'
      coverage-threshold: 80
      enable-secret-scan: true
      post-pr-summary: true
    secrets:
      github-token: ${{ secrets.GITHUB_TOKEN }}
```

---

### Permissions

`pr-sdk.yml` callers need `contents: read`, `checks: write`, `pull-requests: write`, `security-events: write`, and `issues: write`. These scopes cover PR annotations, PR summary comments, and CodeQL SARIF upload. The caller owns the effective token scope under `workflow_call`, so do not rely on the callee's `permissions:` block alone.


## Release Workflow

**Purpose:** Comprehensive release validation and artifact publication.

**When to Use:** Tag-based releases that produce shippable artifacts.

### Library Release Example

```yaml
name: Release

on:
  push:
    tags:
      - 'v*'

permissions:
  contents: write
  packages: write
  id-token: write
  security-events: write

jobs:
  release:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/release.yml@main
    with:
      enable-nuget-publish: true
      nuget-source: 'https://api.nuget.org/v3/index.json'
      create-github-release: true
      release-product-name: 'MyProject'
      release-nuget-packages: |
        MyProject
    secrets:
      nuget-api-key: ${{ secrets.NUGET_API_KEY }}
```

### Container Application Release

```yaml
name: Release

on:
  push:
    tags:
      - 'v*'

permissions:
  contents: write
  packages: write
  id-token: write
  security-events: write

jobs:
  release:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/release.yml@main
    with:
      enable-container-build: true
      dockerfile-path: './Dockerfile'
      container-registry: 'ghcr.io'
      container-image-name: 'honeydrunkstudios/my-app'
      enable-smoke-tests: true
      smoke-test-url: 'https://staging.myapp.com/health'
    secrets:
      container-registry-username: ${{ github.actor }}
      container-registry-password: ${{ secrets.GITHUB_TOKEN }}
```

### Full Release with NuGet and Container

```yaml
name: Release

on:
  push:
    tags:
      - 'v*'
  workflow_dispatch:

jobs:
  release:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/release.yml@main
    with:
      dotnet-version: '10.0.x'
      configuration: 'Release'
      project-path: './src/MyProject.sln'
      enable-nuget-publish: true
      nuget-source: 'https://nuget.pkg.github.com/honeydrunkstudios/index.json'
      enable-container-build: true
      dockerfile-path: './src/MyApp/Dockerfile'
      container-registry: 'ghcr.io'
      container-image-name: 'honeydrunkstudios/my-app'
    secrets:
      nuget-api-key: ${{ secrets.GITHUB_TOKEN }}
      container-registry-username: ${{ github.actor }}
      container-registry-password: ${{ secrets.GITHUB_TOKEN }}

permissions:
  contents: write
  packages: write
  id-token: write
  security-events: write
```

### Worker / Deployable App Release

**When to Use:** Worker services, background processors, or web APIs that need `dotnet publish` artifacts (not NuGet packages, not containers).

```yaml
name: Release

on:
  push:
    tags:
      - 'v*'

permissions:
  contents: write
  packages: write
  id-token: write
  security-events: write

jobs:
  release:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/release.yml@main
    with:
      project-path: './MyProject.slnx'
      enable-app-publish: true
      publish-projects: 'MyWorker/MyWorker.csproj;MyApi/MyApi.csproj'
      publish-runtime: 'linux-x64'
      publish-self-contained: false
    secrets:
      github-token: ${{ secrets.GITHUB_TOKEN }}
```

### Container with Custom Build Context

**When to Use:** Repos where the Dockerfile is not at the repo root, or the build context differs from the working directory (e.g., solution root is a subdirectory).

```yaml
name: Release

on:
  push:
    tags:
      - 'v*'

permissions:
  contents: read
  packages: write
  id-token: write
  security-events: write

jobs:
  release:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/release.yml@main
    with:
      project-path: 'HoneyDrunk.Pulse/HoneyDrunk.Pulse.slnx'
      enable-nuget-publish: true
      enable-container-build: true
      dockerfile-path: 'HoneyDrunk.Pulse/Pulse.Collector/Dockerfile'
      docker-build-context: 'HoneyDrunk.Pulse'
      container-registry: 'myregistry.azurecr.io'
      container-image-name: 'honeydrunkstudios/pulse-collector'
      azure-client-id: ${{ vars.AZURE_CLIENT_ID }}
      azure-tenant-id: ${{ vars.AZURE_TENANT_ID }}
      azure-subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
    secrets:
      nuget-api-key: ${{ secrets.NUGET_API_KEY }}
```

---

### Permissions

`release.yml` callers need `contents: write`, `packages: write`, `id-token: write`, and `security-events: write`. `contents: write` is part of the standard baseline because the reusable release workflow owns GitHub Release creation when `create-github-release: true`; callers that do not create GitHub Releases still use the same baseline so release scaffolds stay uniform. `id-token: write` enables Azure OIDC/SBOM attestation paths, `packages: write` covers package/container publication, and `security-events: write` covers SARIF upload from release-time scans. Missing scopes fail at workflow-load or upload time; broader scopes should be justified by adjacent jobs.

Callers that create GitHub Releases should pass `github-token: ${{ secrets.GITHUB_TOKEN }}` to the reusable workflow. The release workflow falls back to `github.token` for compatibility, but the explicit secret handoff keeps release/package write behavior consistent with other HoneyDrunk reusable workflows.


## Azure Authentication

HoneyDrunk.Actions supports Azure auth through GitHub OIDC federation only.

### OIDC Federation

No long-lived secrets. GitHub issues a short-lived token; Azure trusts it via a federated credential on an App Registration.

**GitHub org variables (non-sensitive):**
- `AZURE_CLIENT_ID` — App Registration client ID
- `AZURE_TENANT_ID` — Azure AD tenant ID
- `AZURE_SUBSCRIPTION_ID` — Target subscription

**Azure side setup:**
1. Create an App Registration
2. Add a federated credential for `repo:HoneyDrunkStudios/<repo>:environment:<env>` (or `:ref:refs/tags/v*` for tag-based releases)
3. Assign roles at narrowest scope: `AcrPush` on ACR, `Website Contributor` on App Service, `Container Apps Contributor` on Container Apps, `Key Vault Secrets User` if reading secrets

```yaml
    with:
      azure-client-id: ${{ vars.AZURE_CLIENT_ID }}
      azure-tenant-id: ${{ vars.AZURE_TENANT_ID }}
      azure-subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
```

### Non-Azure Container Registries

Non-Azure registries may still require registry-native credentials until they are migrated to workload federation.

```yaml
    secrets:
      container-registry-username: ${{ secrets.ACR_USERNAME }}
      container-registry-password: ${{ secrets.ACR_PASSWORD }}
```

---

## Deploy Container to Azure App Service

**Purpose:** Deploy a containerized application to Azure App Service after building with `release.yml`.

**When to Use:** Repos with containerized apps targeting Azure App Service. Chains after the `build-and-scan-container` job in `release.yml`.

### OIDC Example (Recommended)

```yaml
name: Release and Deploy

on:
  push:
    tags:
      - 'v*'

jobs:
  release:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/release.yml@main
    with:
      enable-container-build: true
      dockerfile-path: './Pulse.Collector/Dockerfile'
      container-registry: 'myregistry.azurecr.io'
      container-image-name: 'pulse-collector'
      azure-client-id: ${{ vars.AZURE_CLIENT_ID }}
      azure-tenant-id: ${{ vars.AZURE_TENANT_ID }}
      azure-subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}

  deploy:
    needs: release
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/job-deploy-container.yml@main
    with:
      acr-registry: 'myregistry.azurecr.io'
      container-image: 'myregistry.azurecr.io/pulse-collector:${{ github.ref_name }}'
      app-name: ${{ vars.AZURE_WEBAPP_NAME }}
      resource-group: ${{ vars.AZURE_RESOURCE_GROUP }}
      slot-name: 'staging'
      swap-to-production: true
      health-check-url: '/healthz'
      azure-client-id: ${{ vars.AZURE_CLIENT_ID }}
      azure-tenant-id: ${{ vars.AZURE_TENANT_ID }}
      azure-subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}

permissions:
  contents: read
  packages: write
  id-token: write
```

### Direct-to-Production (No Slot Swap)

```yaml
  deploy:
    needs: release
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/job-deploy-container.yml@main
    with:
      acr-registry: 'myregistry.azurecr.io'
      container-image: 'myregistry.azurecr.io/my-app:${{ github.ref_name }}'
      app-name: 'my-app-service'
      resource-group: 'rg-honeydrunk'
      slot-name: 'production'
      azure-client-id: ${{ vars.AZURE_CLIENT_ID }}
      azure-tenant-id: ${{ vars.AZURE_TENANT_ID }}
      azure-subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
```

### Deploy with Key Vault Secret Injection

Fetch secrets from Azure Key Vault and apply them as App Service configuration before deployment:

```yaml
  deploy:
    needs: release
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/job-deploy-container.yml@main
    with:
      acr-registry: 'myregistry.azurecr.io'
      container-image: 'myregistry.azurecr.io/pulse-collector:${{ github.ref_name }}'
      app-name: 'my-pulse-collector'
      resource-group: 'rg-honeydrunk-prod'
      keyvault-name: 'kv-honeydrunk-prod'
      keyvault-secrets: |
        ConnectionStrings--AppDb
        PostHog--ApiKey=POSTHOG_API_KEY
        Sentry--Dsn=SENTRY_DSN
        ApplicationInsights--ConnectionString
      azure-client-id: ${{ vars.AZURE_CLIENT_ID }}
      azure-tenant-id: ${{ vars.AZURE_TENANT_ID }}
      azure-subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
```

Secret name mapping:
- `ConnectionStrings--AppDb` → env var `ConnectionStrings__AppDb` (auto-converted)
- `PostHog--ApiKey=POSTHOG_API_KEY` → env var `POSTHOG_API_KEY` (explicit mapping)

### Using Key Vault Fetch Standalone

The `azure/keyvault-fetch` action can be used independently in any workflow:

```yaml
    steps:
      - uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/actions/azure/keyvault-fetch@main
        with:
          vault-name: 'kv-honeydrunk-prod'
          secrets: |
            ConnectionStrings--AppDb
            MySecret=MY_ENV_VAR
          export-as: 'env'          # or 'output' or 'both'
          config-file: './appsettings.Production.json'  # optional token substitution
```

---

### Permissions

`job-deploy-container.yml` callers need `contents: read` and `id-token: write`, derived from the callee workflow's declared permissions. `id-token: write` is mandatory for Azure OIDC. Missing it fails before Azure login can run; grant no package or issue scopes unless another job in the same caller needs them.


## Deploy Azure Container App

**Purpose:** Deploy a containerized Node to Azure Container Apps using ADR-0015 revision traffic shifting.

**When to Use:** Containerized HoneyDrunk Nodes named `ca-hd-{service}-{env}` that run in Container Apps with revision mode `Multiple`.

### Minimal Example with Prebuilt Image

```yaml
name: Deploy Container App

on:
  workflow_dispatch:

permissions:
  contents: read
  id-token: write

jobs:
  deploy:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/job-deploy-container-app.yml@main
    with:
      acr-registry: 'acrhdshareddev.azurecr.io'
      container-image: 'acrhdshareddev.azurecr.io/honeydrunk-notify-worker:${{ github.ref_name }}'
      container-app: 'ca-hd-notify-worker-dev'
      resource-group: 'rg-hd-platform-dev'
      health-check-url: '/healthz'
      traffic-shift-mode: 'full'
      azure-client-id: ${{ vars.AZURE_CLIENT_ID }}
      azure-tenant-id: ${{ vars.AZURE_TENANT_ID }}
      azure-subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
```

### Build and Deploy from Docker Context

```yaml
jobs:
  deploy:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/job-deploy-container-app.yml@main
    with:
      acr-registry: 'acrhdshareddev.azurecr.io'
      build-context: '.'
      dockerfile: 'Dockerfile'
      image-name: 'honeydrunk-notify-worker'
      image-tag: ${{ github.ref_name }}
      container-app: 'ca-hd-notify-worker-dev'
      resource-group: 'rg-hd-platform-dev'
      health-check-url: '/healthz'
      azure-client-id: ${{ vars.AZURE_CLIENT_ID }}
      azure-tenant-id: ${{ vars.AZURE_TENANT_ID }}
      azure-subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
```

### Deploy with Key Vault Runtime Secret References

Secret values are not fetched into the workflow. The workflow creates Container App secrets that reference Key Vault and sets env vars to `secretref:` pointers.

```yaml
  deploy:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/job-deploy-container-app.yml@main
    with:
      acr-registry: 'acrhdshareddev.azurecr.io'
      container-image: 'acrhdshareddev.azurecr.io/honeydrunk-notify-worker:${{ github.ref_name }}'
      container-app: 'ca-hd-notify-worker-dev'
      resource-group: 'rg-hd-platform-dev'
      keyvault-name: 'kv-hd-dev'
      keyvault-secrets: |
        ConnectionStrings--AppDb
        Resend--ApiKey=RESEND_API_KEY
        ApplicationInsights--ConnectionString
      azure-client-id: ${{ vars.AZURE_CLIENT_ID }}
      azure-tenant-id: ${{ vars.AZURE_TENANT_ID }}
      azure-subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
```

Secret name mapping:
- `ConnectionStrings--AppDb` -> env var `ConnectionStrings__AppDb`
- `Resend--ApiKey=RESEND_API_KEY` -> env var `RESEND_API_KEY`

### Inputs

| Input | Required | Default | Description |
|---|---:|---|---|
| `runs-on` | No | `ubuntu-latest` | GitHub runner label. |
| `container-image` | Conditional | `''` | Full image reference. Required when `build-context` is empty. |
| `build-context` | No | `''` | Docker build context. When set, the workflow builds and pushes before deploy. |
| `image-name` | Conditional | `''` | Short image name. Required with `build-context`. |
| `image-tag` | Conditional | `''` | Explicit image tag. Required with `build-context`. |
| `dockerfile` | No | `Dockerfile` | Dockerfile path relative to `build-context`. |
| `acr-registry` | Yes | n/a | ACR login server. |
| `container-app` | Yes | n/a | Target Container App. Must match `ca-hd-{service}-{env}`. |
| `resource-group` | Yes | n/a | Resource group containing the Container App. |
| `revision-suffix` | No | `ca-${{ github.run_id }}-${{ github.run_attempt }}` | Traceable suffix for the new revision. |
| `health-check-url` | No | `''` | Absolute URL or path relative to the revision FQDN. Empty skips probing. |
| `health-check-timeout` | No | `120` | Seconds to wait for revision readiness and health. |
| `startup-wait` | No | `15` | Seconds to wait after revision reaches Running before probing. |
| `traffic-shift-mode` | No | `full` | `full`, `hold`, or `canary:N`. |
| `keyvault-name` | No | `''` | Key Vault used for runtime secret references. |
| `keyvault-secrets` | No | `''` | Newline-separated `SECRET_NAME` or `SECRET_NAME=ENV_VAR_NAME`. |
| `azure-client-id` | Yes | n/a | Azure client ID for OIDC federation. |
| `azure-tenant-id` | Yes | n/a | Azure tenant ID for OIDC federation. |
| `azure-subscription-id` | Yes | n/a | Azure subscription ID for OIDC federation. |
| `actions-ref` | No | `''` | Ref of `HoneyDrunk.Actions` to check out for composite actions. Empty uses the called workflow ref. |

### Outputs

| Output | Description |
|---|---|
| `revision-name` | Created Container App revision name. |
| `revision-fqdn` | Revision-specific FQDN when available. |
| `deployment-status` | `success`, `health-check-failed`, or `deploy-failed`. |

### Traffic Shift Modes

| Mode | Behavior |
|---|---|
| `full` | Shift 100% of traffic to the new revision after health succeeds. |
| `hold` | Leave the new revision active at 0% traffic for manual validation. |
| `canary:N` | Shift `N` percent to the new revision and keep the remainder on the previous traffic target. |

### Target Prerequisites

- Runners need `python3`, Azure CLI with Container Apps support, `jq`, Bash, and `curl`; the default GitHub-hosted Ubuntu runner supplies these. Self-hosted runners must provision them.
- Container App name must match `ca-hd-{service}-{env}`.
- Container App `activeRevisionsMode` must be `Multiple`.
- Container App must have system-assigned Managed Identity enabled.
- Ingress must route 100% to exactly one explicitly named revision. Positive `latestRevision` routing, split traffic, empty/unknown traffic, malformed responses, and traffic-read errors fail before build or deployment. Zero-weight entries are permitted. The workflow never guesses a current revision from the active revision list.
- Coordinate all writers for the app: serialize application rollouts, manual rollbacks, and Infrastructure maintenance. The captured traffic target is rechecked before Key Vault/environment mutation, immediately before candidate creation, and before traffic shifting (including `hold`); a changed target fails instead of overwriting another rollout. These reads are guardrails, not an atomic Azure lock.
- For Key Vault references, that managed identity must have access to the referenced Key Vault secrets.
- For OIDC deploys, the federated credential needs `AcrPush` on the shared ACR and `Container Apps Contributor` on the target Container App.

---

### Bootstrap and Infrastructure ownership

Bootstrap must establish a healthy placeholder or application revision before this rollout workflow is used. Its named traffic target must already exist; this workflow does not create a missing app or automatically pin `latestRevision` traffic. Infrastructure should stop writing the application image and traffic after initialization, or require an explicit approved maintenance snapshot. Reapplying a stale image or `latestRevision: true` restores the same unsafe contract.

For an existing app using `latestRevision`, perform a separately approved migration with deployments paused: read the current traffic and the actual ready revision receiving it, verify identity/readiness and health, then pin the same revision at 100%. Re-read traffic and health before retrying the application release. Do not pick the last active revision or assume `latestRevisionName` is serving traffic while a newer revision is still provisioning. Named traffic must be explicit in subsequent IaC applies. See the [Infrastructure Pulse lifecycle](https://github.com/HoneyDrunkStudios/HoneyDrunk.Infrastructure/tree/main/nodes/pulse) for its initialization and maintenance contract.

A canary leaves two traffic-bearing revisions intentionally. Before the next rollout, an operator must deliberately finish or roll back that canary to a single known-good named 100% target. Automatic consolidation is not performed.

`deployment-status` remains `success`, `health-check-failed`, or `deploy-failed`. Success requires the whole job so far to be successful, a completed revision deployment, a successful requested health probe, and a completed traffic step. Checkout, setup, preflight, Azure-read errors, cancellation, or skipped required stages cannot report success. If cancellation prevents the final status step itself from running, its output can be absent: callers must use the job result as authoritative. Summary traffic percent is `not confirmed` when the shift step produced no confirmed outcome.

These changes preserve the existing health-probe inputs and their semantics. A relative `health-check-url` is intended to target the candidate's revision-specific FQDN; empty input skips the HTTP probe. Existing absolute-URL and app-FQDN-fallback behavior is unchanged and is not evidence that a particular candidate passed an application-level probe.

### Permissions

`job-deploy-container-app.yml` callers need `contents: read` and `id-token: write`, derived from the callee workflow's declared permissions. The caller controls the effective OIDC token grant under `workflow_call`; missing `id-token: write` breaks deployment before any Azure command runs.


## Deploy Azure Function App

**Purpose:** Deploy a .NET Azure Function App after building with the reusable `.NET publish artifact` job.

**When to Use:** Repos with Azure Function Apps (queue-triggered, HTTP-triggered, timer-triggered, etc.). Chain `job-dotnet-publish-artifact.yml` into `job-deploy-function.yml` so consumer repos do not reimplement checkout, setup, restore, build, test, publish, or artifact upload.

### Minimal Example

```yaml
name: Release and Deploy Function

on:
  push:
    tags:
      - 'v*'

jobs:
  build:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/job-dotnet-publish-artifact.yml@main
    with:
      project-path: 'MyProject.slnx'
      publish-project: 'MyProject.Functions/MyProject.Functions.csproj'
      artifact-name: 'function-app'
      publish-output: './publish'

  deploy:
    needs: build
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/job-deploy-function.yml@main
    with:
      functions-app: 'my-function-app'
      resource-group: 'rg-honeydrunk'
      azure-client-id: ${{ vars.AZURE_CLIENT_ID }}
      azure-tenant-id: ${{ vars.AZURE_TENANT_ID }}
      azure-subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}

permissions:
  contents: read
  id-token: write
```

### Deploy with Slot Swap

```yaml
  deploy:
    needs: build
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/job-deploy-function.yml@main
    with:
      functions-app: 'my-function-app'
      resource-group: 'rg-honeydrunk'
      slot-name: 'staging'
      swap-to-production: true
      health-check-url: '/api/health'
      azure-client-id: ${{ vars.AZURE_CLIENT_ID }}
      azure-tenant-id: ${{ vars.AZURE_TENANT_ID }}
      azure-subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
```

### Deploy with Key Vault Secret Injection

```yaml
  deploy:
    needs: build
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/job-deploy-function.yml@main
    with:
      functions-app: 'notify-dispatcher'
      resource-group: 'rg-honeydrunk-prod'
      keyvault-name: 'kv-honeydrunk-prod'
      keyvault-secrets: |
        NotifyQueueConnection=NOTIFY_QUEUE_CONNECTION
        Resend--ApiKey=RESEND_API_KEY
        Twilio--AccountSid=TWILIO_ACCOUNT_SID
        Twilio--AuthToken=TWILIO_AUTH_TOKEN
      azure-client-id: ${{ vars.AZURE_CLIENT_ID }}
      azure-tenant-id: ${{ vars.AZURE_TENANT_ID }}
      azure-subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
```

---

### Permissions

`job-dotnet-publish-artifact.yml` callers need `contents: read`. `job-deploy-function.yml` callers need `contents: read` and `id-token: write`, derived from the callee workflow's declared permissions. Keep function build and function deploy as reusable-workflow jobs; consumer repos should not carry local checkout/setup-dotnet/upload-artifact steps.


## Nightly Security Workflow

**Purpose:** Deep, comprehensive security scanning on a schedule.

**When to Use:** All repos. Schedule for off-hours to avoid interrupting development.

### Basic Example

```yaml
name: Nightly Security Scan

on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM UTC daily
  workflow_dispatch:

jobs:
  security-scan:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/nightly-security.yml@main
    secrets:
      github-token: ${{ secrets.GITHUB_TOKEN }}

permissions:
  actions: read
  contents: read
  security-events: write
  issues: write
```

### Full Example with Issue Creation

```yaml
name: Nightly Security Scan

on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM UTC daily
  workflow_dispatch:

jobs:
  security-scan:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/nightly-security.yml@main
    with:
      dotnet-version: '10.0.x'
      project-path: './src/MyProject.sln'
      enable-sast: true
      enable-iac-scan: true
      enable-secret-scan: true
      fail-on-high-severity: false  # Don't fail, just report
      create-issues: true
    secrets:
      github-token: ${{ secrets.GITHUB_TOKEN }}

permissions:
  actions: read
  contents: read
  security-events: write
  issues: write
```

---

### Permissions

`nightly-security.yml` callers need `actions: read`, `contents: read`, `security-events: write`, and `issues: write`. `actions: read` lets CodeQL read workflow-run metadata while finalizing analysis; `security-events: write` uploads SARIF to GitHub Code Scanning when Code Security is enabled; `issues: write` lets the workflow maintain tracking issues. The reusable workflow does not grant caller permissions on its own, so callers should carry the full permission baseline. During rollout, callers missing `actions: read` get runtime CodeQL finalization degradation with a warning only when CodeQL has already exported SARIF; other missing baseline permissions remain caller defects and may still surface as failed or stale scheduled runs in grid-health. The filtered SAST SARIF upload is best-effort for repositories without Code Security; failed uploads emit a warning and job-summary entry, and the workflow still uploads the SARIF artifact report.

### Node and Rust Audit Jobs

For TypeScript/Rust repos that do not need the .NET-oriented nightly security workflow, call the focused reusable audit jobs directly:

```yaml
name: Nightly Security

on:
  schedule:
    - cron: '0 9 * * 1'
  workflow_dispatch:

permissions:
  contents: read

jobs:
  node-audit:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/job-node-security-audit.yml@main
    with:
      node-version-file: .nvmrc

  rust-audit:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/job-rust-security-audit.yml@main
```

`job-node-security-audit.yml` and `job-rust-security-audit.yml` callers need `contents: read`. They upload JSON audit artifacts and fail when their underlying audit command reports blocking findings.


## Nightly Dependencies Workflow

**Purpose:** Detect outdated dependencies and optionally create update PRs.

**When to Use:** All repos. Schedule for weekday mornings for visibility.

### Basic Report-Only Example

```yaml
name: Nightly Dependency Check

on:
  schedule:
    - cron: '0 3 * * 1-5'  # 3 AM UTC weekdays
  workflow_dispatch:

jobs:
  dependency-check:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/nightly-deps.yml@main
    with:
      check-dotnet-deps: true
      check-npm-deps: false
      create-update-prs: false
    secrets:
      github-token: ${{ secrets.GITHUB_TOKEN }}

permissions:
  contents: write
  pull-requests: write
  issues: write
```

The report-only dependency workflow also maintains one issue titled `📦 Outdated Dependencies` in the consumer repo. The body is replaced on every run with the current outdated package set, reopened when packages fall behind again, and closed automatically when everything is current. Do not hand-create or hand-edit that issue; grant `issues: write` so the workflow can maintain it.

### With Auto-PR Creation

```yaml
name: Nightly Dependency Check

on:
  schedule:
    - cron: '0 3 * * 1-5'  # 3 AM UTC weekdays
  workflow_dispatch:

jobs:
  dependency-check:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/nightly-deps.yml@main
    with:
      dotnet-version: '10.0.x'
      node-version: '20.x'
      check-dotnet-deps: true
      check-npm-deps: true
      create-update-prs: true
      pr-branch-prefix: 'deps/auto-update'
      group-updates: true
      exclude-prerelease: true
    secrets:
      github-token: ${{ secrets.GITHUB_TOKEN }}

permissions:
  contents: write
  pull-requests: write
  issues: write
```

---

### Permissions

`nightly-deps.yml` callers need `contents: write`, `pull-requests: write`, and `issues: write`. Contents and pull-request writes are required when update PR creation is enabled; issues write maintains the dependency tracking issue. Report-only callers may not need every write path at runtime, but the canonical scaffold grants the reusable workflow's full supported surface so toggling `create-update-prs` does not require a permissions edit.

### Node and Rust Report Jobs

For TypeScript/Rust repos that only need report artifacts and do not need update PR automation, call the focused reusable report jobs directly:

```yaml
name: Nightly Dependencies

on:
  schedule:
    - cron: '0 8 * * 1'
  workflow_dispatch:

permissions:
  contents: read

jobs:
  node-deps:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/job-node-dependency-report.yml@main
    with:
      node-version-file: .nvmrc

  rust-deps:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/job-rust-dependency-report.yml@main
```

`job-node-dependency-report.yml` and `job-rust-dependency-report.yml` callers need `contents: read`. These jobs upload dependency artifacts only; they do not maintain the grouped dependency issue or create update PRs.


## Nightly Accessibility Workflow

**Purpose:** Comprehensive WCAG accessibility scanning for web/UI repos.

**When to Use:** Web apps, UI libraries. Opt-in only for applicable repos.

### .NET Web App Example

```yaml
name: Nightly Accessibility Scan

on:
  schedule:
    - cron: '0 4 * * 2,5'  # 4 AM UTC Tuesday and Friday
  workflow_dispatch:

jobs:
  accessibility-scan:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/nightly-accessibility.yml@main
    with:
      build-type: 'dotnet-web'
      base-url: 'http://localhost:5000'
      routes: '/,/about,/contact,/products'
      wcag-level: 'AA'
      create-tracking-issue: true
    secrets:
      github-token: ${{ secrets.GITHUB_TOKEN }}

permissions:
  contents: read
  issues: write
```

### Storybook Example

```yaml
name: Nightly Accessibility Scan

on:
  schedule:
    - cron: '0 4 * * 2,5'  # 4 AM UTC Tuesday and Friday
  workflow_dispatch:

jobs:
  accessibility-scan:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/nightly-accessibility.yml@main
    with:
      build-type: 'storybook'
      base-url: 'http://localhost:6006'
      wcag-level: 'AA'
      violation-threshold: 5
      create-tracking-issue: true
    secrets:
      github-token: ${{ secrets.GITHUB_TOKEN }}

permissions:
  contents: read
  issues: write
```

### Custom Build with Routes File

```yaml
name: Nightly Accessibility Scan

on:
  schedule:
    - cron: '0 4 * * 2,5'
  workflow_dispatch:

jobs:
  accessibility-scan:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/nightly-accessibility.yml@main
    with:
      build-type: 'custom'
      build-command: 'npm run build && npm run serve'
      base-url: 'http://localhost:3000'
      routes-file: './accessibility-routes.txt'
      wcag-level: 'AAA'
      create-tracking-issue: true
    secrets:
      github-token: ${{ secrets.GITHUB_TOKEN }}

permissions:
  contents: read
  issues: write
```

---

### Permissions

`nightly-accessibility.yml` callers need `contents: read` and `issues: write`, derived from the callee workflow's declared permissions. Issues write is required when `create-tracking-issue` is enabled. Missing caller permissions fail at workflow-load time; extra scopes are discouraged.


## Weekly Governance Workflow

**Purpose:** Organization-wide governance checks for policy compliance.

**When to Use:** Dedicated governance/meta repo. Requires org-level token.

### Basic Example

```yaml
name: Weekly Governance Scan

on:
  schedule:
    - cron: '0 8 * * 1'  # 8 AM UTC Monday
  workflow_dispatch:

jobs:
  governance-scan:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/weekly-governance.yml@main
    secrets:
      github-token: ${{ secrets.ORG_ADMIN_TOKEN }}

permissions:
  contents: read
  issues: write
```

### Full Example with Custom Requirements

```yaml
name: Weekly Governance Scan

on:
  schedule:
    - cron: '0 8 * * 1'  # 8 AM UTC Monday
  workflow_dispatch:

jobs:
  governance-scan:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/weekly-governance.yml@main
    with:
      organization: 'HoneyDrunkStudios'
      required-workflows: 'pr-core,pr-sdk'
      required-files: 'README.md,LICENSE,CODEOWNERS,SECURITY.md'
      exclude-repos: 'archive-repo-1,temp-fork'
      exclude-archived: true
      check-stale-branches: true
      stale-branch-days: 90
      check-stale-prs: true
      stale-pr-days: 30
      create-issues: true
    secrets:
      github-token: ${{ secrets.ORG_ADMIN_TOKEN }}

permissions:
  contents: read
  issues: write
```

---

### Permissions

`weekly-governance.yml` callers need `contents: read` and `issues: write`, derived from the callee workflow's declared permissions. The org token may have broader repository access, but the workflow token should still be scoped to the minimum needed by the reusable workflow.


## Multi-Workflow Example

Many repos will want to combine multiple workflows:

```yaml
# .github/workflows/ci-cd.yml
name: CI/CD Pipeline

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]
    tags:
      - 'v*'
  schedule:
    - cron: '0 2 * * *'  # Nightly security
  workflow_dispatch:

permissions:
  actions: read
  contents: write
  checks: write
  pull-requests: write
  packages: write
  id-token: write
  security-events: write
  issues: write

jobs:
  # PR validation
  pr-validation:
    if: github.event_name == 'pull_request'
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/pr-sdk.yml@main
    with:
      coverage-threshold: 80
    secrets:
      github-token: ${{ secrets.GITHUB_TOKEN }}

  # Release on tags
  release:
    if: startsWith(github.ref, 'refs/tags/v')
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/release.yml@main
    with:
      enable-nuget-publish: true
    secrets:
      nuget-api-key: ${{ secrets.NUGET_API_KEY }}

  # Nightly security scan
  security-scan:
    if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/nightly-security.yml@main
    secrets:
      github-token: ${{ secrets.GITHUB_TOKEN }}
```

---

## Tips and Best Practices

### Version Pinning

For production stability, pin to a specific version tag instead of `@main`:

```yaml
uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/pr-core.yml@v1.0.0
```

### Permissions

Always specify minimum required permissions:

```yaml
permissions:
  contents: read      # Checkout code
  checks: write       # Publish test results
  pull-requests: write  # Comment on PRs
```

### Secrets

Use GitHub secrets for sensitive data:

```yaml
secrets:
  nuget-api-key: ${{ secrets.NUGET_API_KEY }}
  github-token: ${{ secrets.GITHUB_TOKEN }}  # Built-in token
```

### Workflow Dispatch

Add `workflow_dispatch` to allow manual triggering:

```yaml
on:
  schedule:
    - cron: '0 2 * * *'
  workflow_dispatch:  # Enables "Run workflow" button
```

### Multiple Environments

Use matrix strategy for multi-platform testing:

```yaml
permissions:
  contents: read
  checks: write
  pull-requests: write
  security-events: write
  issues: write

jobs:
  pr-validation-linux:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/pr-core.yml@main
    with:
      runs-on: 'ubuntu-latest'

  pr-validation-windows:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/pr-core.yml@main
    with:
      runs-on: 'windows-latest'
```

---

## Troubleshooting

### Common Issues

**Problem:** Workflow not found  
**Solution:** Ensure the path and ref are correct. Check that HoneyDrunk.Actions repo is public or you have access.

**Problem:** Permission denied  
**Solution:** Check that required permissions are specified in the calling workflow.

**Problem:** Secrets not passed  
**Solution:** Secrets must be explicitly passed. `secrets: inherit` passes all secrets.

**Problem:** Workflow takes too long  
**Solution:** Use `pr-core` for PRs. Save deep scans for scheduled workflows.

### Getting Help

- Check workflow run logs for detailed error messages
- Review the workflow source in HoneyDrunk.Actions repository
- Open an issue in HoneyDrunk.Actions for bugs or feature requests

---

## Migration Guide

### From Existing CI

1. **Identify your workflow type:**
   - Basic CI ? `pr-core`
   - Library/SDK ? `pr-sdk`
   - Release process ? `release`

2. **Replace your existing workflow:**
   ```yaml
   # Old
   jobs:
     build:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v5
         - name: Setup .NET
           uses: actions/setup-dotnet@v5
         # ... many more steps

   # New
   jobs:
     pr-validation:
       uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/pr-core.yml@main
   ```

3. **Add scheduled workflows:**
   - Add `nightly-security.yml` for security scans
   - Add `nightly-deps.yml` for dependency management

4. **Test incrementally:**
   - Start with PR workflows
   - Add release workflows after PR validation works
   - Add scheduled workflows last

---

## Notifications

Use the `common/send-notification` composite action to send Slack or Teams messages from any workflow step.

### Slack Notification on Failure

```yaml
- name: Notify Slack on failure
  if: failure()
  uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/actions/common/send-notification@main
  with:
    slack-webhook-url: ${{ secrets.SLACK_WEBHOOK_URL }}
    status: failure
    title: 'Build Failed'
    message: 'Build failed on ${{ github.ref_name }}'
    fields: |
      Repo=${{ github.repository }}
      Run=${{ github.run_id }}
    url: '${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}'
```

### Teams Notification on Success

```yaml
- name: Notify Teams on success
  if: success()
  uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/actions/common/send-notification@main
  with:
    teams-webhook-url: ${{ secrets.TEAMS_WEBHOOK_URL }}
    status: success
    title: 'Deployment Complete'
    message: 'Version ${{ needs.build.outputs.version }} deployed to production'
    url: '${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}'
```

---

## Support

For questions, issues, or feature requests:
- **Repository:** https://github.com/HoneyDrunkStudios/HoneyDrunk.Actions
- **Issues:** https://github.com/HoneyDrunkStudios/HoneyDrunk.Actions/issues
- **Documentation:** This file and workflow headers
