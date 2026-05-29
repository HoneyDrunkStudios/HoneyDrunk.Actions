# Changelog

All notable changes to the GitHub Actions template library will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- `job-sonarcloud.yml`: exclude consumer `.github/workflows/**` wrapper YAML from SonarQube Cloud source analysis by default. The wrapper workflows intentionally call first-party reusable workflows from `HoneyDrunk.Actions@main` so repos receive centralized workflow fixes; SonarCloud reports those new wrapper calls as Security Hotspots even though the executable workflow logic is governed in this repo. Consumers can override the new `sonar-exclusions` input when they intentionally want Sonar to scan workflow YAML.

- `actions/dotnet/test`: repaired the coverage-runsettings heredoc emitted by the composite action and added the supported `no-restore` input that `job-dotnet-publish-artifact.yml` already passes. The heredoc terminator now reaches Bash at column 1, so test jobs no longer exit before `dotnet test` can produce results and coverage.

- `actions/dotnet/test` and `job-sonarcloud.yml`: preserve consumer-owned coverlet runsettings when adding native OpenCover output. The previous native-OpenCover fix wrote a format-only `coverlet.runsettings` and passed it via `--settings`, which unintentionally replaced repo filters such as `<Include>`, `<ExcludeByFile>`, and `<IncludeTestAssembly>`. In Pulse, that pulled generated `obj` sources into the denominator and dropped reported line coverage from 71.0% to 27.9% without a real test regression. The generated CI runsettings now starts from `coverage-runsettings` or `coverlet.runsettings` in the working directory when present, then merges in `<Format>opencover,cobertura</Format>`.

- `pr-core.yml` coverage gate: enforce total baseline/floor coverage even when patch coverage is `n/a` because no executable lines changed. Patch coverage remains skipped in that case, but the repo-level total gate now keeps catching instrumentation or baseline regressions in infra-only PRs.

- `pr-core.yml` NuGet Version Consistency Check + PR Summary and Coverage Gate + PR Size Check: tolerate non-UTF-8 bytes in `git diff` output. The gates' Python scripts used `subprocess.run(..., text=True)` which decodes stdout as strict UTF-8 and crashed with `UnicodeDecodeError` whenever a PR's diff context happened to include a Latin-1 byte (e.g. a raw `×` 0xd7 or `±` 0xb1 in a removed/added docstring). The bytes were unrelated to the gate's actual concerns (`+/- <Version>` lines and file headers), so the crash was pure incidental fragility. Now those `subprocess.run` calls capture stdout as bytes and decode with `errors='replace'`. Surfaced by HoneyDrunk.Transport PR #39.

- `pr-core.yml` coverage gate: compare baseline at displayed precision (1 decimal) instead of raw float, eliminating false-negative failures where the gate reported `total 70.9% < baseline 70.9% (D2)` — same displayed percentage, but the underlying float was strictly less than the baseline (e.g., `70.864 < 70.9`). The ratchet's intent is to prevent visible coverage regressions; the comparison now matches what reviewers actually see. The floor comparison (D3) also rounds to 1 decimal for the same reason. Blocked Kernel#63 (a findings-triage PR with no executable line changes) until this fix landed.

- `actions/dotnet/test`, `job-build-and-test.yml`, `job-sonarcloud.yml`: emit OpenCover natively from `coverlet.collector` via a runsettings file (`<Format>opencover,cobertura</Format>`) instead of post-hoc Cobertura → OpenCover conversion. Root cause: ReportGenerator's OpenCover output is a paid-only feature (`OpenCover output format is only available for sponsors`), so the conversion silently produced no file and SonarCloud imported zero coverage despite the analysis succeeding. The dotnet/test composite now writes a coverlet runsettings to the results directory and passes `--settings` alongside `--collect "XPlat Code Coverage"`; `job-build-and-test.yml`'s upload step now globs both `coverage.cobertura.xml` (consumed by coverage-baseline-ratchet and report-generator) and `coverage.opencover.xml` (consumed by SonarQube Cloud). `job-sonarcloud.yml` drops the ReportGenerator install and the convert step entirely, and its push:main fallback uses the same runsettings approach so main-branch analysis also emits OpenCover natively. Closes ADR-0011 coverage-import regression.

- `job-sonarcloud.yml`: add a coverage-generation fallback for `push:main` runs. PR runs reuse the coverage artifact published by the caller's `pr-core` job (cost-disciplined per ADR-0011 D11). On `push:main` runs there's no `pr-core` (it's gated to `pull_request`), so no upstream test job runs and no artifact exists — leaving the SonarCloud Overview dashboard coverage metric stuck at 0% and giving the leak-period baseline no coverage to compare against. New conditional step now runs `dotnet test` with coverage collection only when no coverage artifact is found from the download step. PR runs are unchanged (the conditional is a no-op when the artifact is present). Steps reordered: begin → build → (conditional test) → end, so coverage is generated after build but before the scanner reads it. _(Superseded later in this unreleased range by the native-OpenCover-emission fix above — both PR and push:main paths now request OpenCover directly via a coverlet runsettings file, removing the convert step entirely.)_

- `job-sonarcloud.yml`: re-add the `/d:sonar.cs.opencover.reportsPaths="**/coverage.opencover.xml"` flag to the `dotnet-sonarscanner begin` invocation. The earlier removal expected per-repo `sonar-project.properties` to provide the path, but `.properties` files are then rejected by SonarScanner for .NET and were deleted in the consumer onboarding PRs. With no `.properties` file and no CLI flag, the scanner had no way to find the OpenCover report — coverage silently never imported, undermining ADR-0011 D11's quality-gate intent. Now the flag is the default in the reusable workflow; per-repo overrides remain available via MSBuild `<SonarQubeSetting>` items in `Directory.Build.props`.

### Added

- `.github/config/labels.json`: added ADR-0086 worker-state labels (`needs-agent-review`, `agent-review-in-progress`, `agent-reviewed`, `changes-requested-by-agent`) plus the managed PR-label vocabulary used by the upcoming label-normalizing review enqueue workflow.

- `job-sonarcloud-quality-gate.yml` and `pr-core.yml`: added an opt-in ADR-0011 D11 SonarQube Cloud quality gate that polls PR new-code metrics (`new_violations`, `new_bugs`, `new_vulnerabilities`, `new_code_smells`, and `new_security_hotspots`) and compares them against configurable thresholds. The default posture is no behavior change (`enable-sonar-quality-gate: false`) and soft launch when enabled (`sonar-quality-gate-mode: warn`); repos can flip to `enforce` after observing real PRs. Breaches surface in the check annotations and PR summary so SonarQube Cloud's free-tier default gate no longer silently passes PRs that introduce new issues or hotspots.

- `release.yml`: added centralized GitHub Release creation with generated HoneyDrunk release notes. Consumers now pass release metadata (`release-product-name`, `release-product-description`, `release-nuget-packages`, `release-docs-url`) into the reusable release workflow instead of carrying repo-local checkout/generate-notes/`softprops/action-gh-release` jobs.

- `job-solution-preflight.yml`: new reusable scaffold preflight job for repos whose solution or project path may not exist yet. Consumer repos can gate PR/nightly/release callers without duplicating local `actions/checkout` + file-exists shell snippets.

- `job-dotnet-publish-artifact.yml`: new reusable build/test/publish artifact job for deployable .NET projects, especially Azure Function Apps that hand an artifact to `job-deploy-function.yml`.

- `pr-core.yml`: new `NuGet Version Consistency Check` job that runs alongside the other PR Core checks (`authorship-check` / `pr-metadata-check` / `pr-size-check`). When a PR bumps the `<Version>` of any NuGet-publishing `.csproj` (i.e. a project with a `<PackageId>`), the gate enforces three invariants: (1) every NuGet-publishing csproj in the repo shares the same `<Version>` — no drift between, e.g., a runtime package and its abstractions; (2) every NuGet-publishing csproj's per-package `CHANGELOG.md` carries a `## [<new-version>]` heading — content under `## [Unreleased]` does not satisfy the gate; (3) the repo-level `CHANGELOG.md` sitting next to a `.slnx` also has a `## [<new-version>]` heading. No-op for repos with zero NuGet-publishing csprojs and no-op when the PR doesn't touch any `<Version>` element, so safe to default on across the Grid. Motivated by Kernel v0.8.0's silent `Create GitHub Release` failure (release-notes generator awk-greps for `## [VERSION]` and exited 1 when the section was still labeled `## [Unreleased]`); this gate refuses such PRs up front instead of catching the problem at tag-push time, after NuGet has already published. Wired into the PR summary comment alongside the other check results.

- `pr-core.yml` coverage gate: display branch and method coverage alongside line coverage in the gate verdict and PR summary. Coverlet's Cobertura output carries all three metrics; previously the gate only surfaced line coverage. Branch coverage parses the `condition-coverage="X% (covered/total)"` attribute from `<line branch="true">` elements; method coverage counts `<method>` elements whose `<line>` children have any hits. Both metrics dedupe across multiple coverage files via the same canonical source-file key used for line coverage (so a source file exercised by two test projects doesn't double-count). The gate continues to ratchet line coverage only (per ADR-0011 D2) — branch and method are informational. Display format: `Total coverage: 70.9% line / 51.3% branch / 82.4% method`. Follow-up work to ratchet branch and method per consumer opt-in is scoped in HoneyDrunkStudios/HoneyDrunk.Architecture#445.

- `job-sonarcloud.yml`: new tier-2 reusable workflow that runs SonarQube Cloud (formerly SonarCloud) static analysis on a .NET repo via `dotnet-sonarscanner`. Reuses the coverage artifact from `job-build-and-test.yml` (no double `dotnet test`); the upstream test step emits OpenCover natively via coverlet runsettings, which the scanner reads directly. Reports the SonarQube Cloud quality gate as a PR check. Job-level `if:` guard enforces `pull_request` + `push:main` only as defence in depth for ADR-0011 D11 cost discipline. Inputs include `working-directory` (supports inner-subdir Pattern A layouts), `sonar-organization`, `sonar-project-key`, and `coverage-artifact-name`. Per ADR-0011 packet 02.

### Changed

- `seed-labels-fanout.yml`: refreshed the default Grid fan-out target list so the labels-as-code seed reaches newer repos, including Audit, Observe, AI, Operator, Flow, Memory, Knowledge, Capabilities, Agents, Lore, Standards, `.github`, and TheHive.

- `docs/consumer-usage.md`: documented the standard caller split. Consumer workflows own triggers, version/environment resolution, and repo-specific metadata only; reusable workflow mechanics stay in `HoneyDrunk.Actions`.

- `actions-ci.yml`: chose D4 Outcome B for `docker://` refs and migrated actionlint to direct install-and-invoke.
- `agent-run.yml`: added optional `packet-path` input. When supplied, the workflow (1) injects a structured `> Packet: <permalink>` instruction into the agent's prompt envelope and (2) runs a post-hoc "Assert PR-body packet link" step that mechanically inserts the canonical line into any PR the agent opened in the `checkout-target` repo. The workflow — not the LLM — is the mechanical guarantor of invariant 32 in HoneyDrunk.Architecture. The permalink resolves to the Architecture checkout's actual commit SHA (via `git rev-parse HEAD`) so the link is immutable, not a moving branch ref. Idempotent (no edit if the canonical line is already present) and soft on edge cases (no PR / no checkout-target / detached HEAD / main-branch run → notice + exit 0). Existing callers unaffected — `packet-path` defaults to empty. Per ADR-0011 packet 03.
- `docs/action-pins.md`: added the ADR-0012 D10 third-party action pin inventory.
- `docs/d4-retrofit-audit.md`: recorded the D4 retrofit audit and `docker://` policy clarification.
- `grid-health-report.yml`: added the ADR-0012 D6 Grid Health aggregator workflow, shell implementation, and operator guide.
- `release.yml`: migrated Trivy and SBOM generation from marketplace wrappers to direct Trivy/Syft CLI invocation per ADR-0012 D4.

### Removed

- Removed the unused `release/extract-changelog` composite action. `release/generate-notes` owns changelog discovery/extraction and was the only supported release-notes path.

## [1.0.1] - 2026-04-18

### Added
- `coverage-baseline-ratchet.yml`: push-only reusable workflow for maintaining `.github/coverage-baseline.json` with `contents: write`, letting PR validation callers keep `contents: read`.
- `job-dependency-scan.yml`: PR-time vulnerable-package scan (`dotnet list package --vulnerable --include-transitive`). Emits severity counts, uploads JSON report artifact, fails on configurable severity threshold.
- `pr-core.yml`: wired in the dependency-scan job as optional (default on), with `enable-dependency-scan` and `dependency-fail-on-severity` inputs. Results appear in the PR summary comment alongside existing jobs.
- `pr-sdk.yml`: same dependency-scan wiring for SDK/library repos; findings + severity breakdown show up in the SDK PR comment.
- `job-codeql.yml`: PR-time CodeQL SAST + code-quality scan using the `security-and-quality` query pack (same suite nightly runs). Uploads SARIF to Code Scanning under a `pr-sast` category, emits severity counts, and fails the PR at or above a configurable SARIF level (default: any finding).
- `pr-core.yml` and `pr-sdk.yml`: wired in the CodeQL job as optional (default on) with `enable-codeql`, `codeql-queries`, and `codeql-fail-on-severity` inputs. Findings + severity breakdown appear in the PR summary comment.

### Changed
- `pr-core.yml`: removed default-branch baseline ratcheting from PR validation orchestration so consumer PR workflows no longer require `contents: write`.
- `docs/consumer-usage.md`: updated coverage gate examples to split read-only PR validation from write-capable default-branch ratcheting.
- `job-static-analysis.yml`: removed the vulnerability scan step (now owned by `job-dependency-scan.yml`) and dropped its `fail-on-severity` input. `pr-core.yml` and `pr-sdk.yml` no longer pass that input.

## [1.0.0] - 2025-01-07

### Added
- Initial release of GitHub Actions template library
- Composite actions for .NET SDK operations
  - Setup: Install .NET SDK with version control
  - Restore: Restore NuGet packages with verbosity control
  - Build: Build projects with configuration options
  - Test: Run tests with coverage collection
  - Pack: Create NuGet packages
  - Publish: Publish applications for deployment
- Composite actions for NuGet operations
  - Setup Cache: Configure NuGet package caching
  - Push: Push packages to NuGet feeds
  - Add Source: Add custom NuGet sources
- Composite actions for diagnostics
  - Debug Build Identity: Display environment information
  - Validate Test Naming: Check test file naming conventions
  - Publish Test Results: Upload and annotate test results
- Composite actions for security
  - Vulnerability Scan: Scan for known security vulnerabilities
- Composite actions for PR operations
  - Generate Summary: Create build summaries for PRs
  - Post Comment: Post automated comments on PRs
- Reusable workflows
  - Build and Test: Complete CI pipeline with testing
  - Code Quality: Security and quality checks
  - Publish NuGet: Full package publishing workflow
  - PR Validation: Comprehensive PR validation
- Example workflows
  - Simple CI workflow
  - Multi-platform build matrix
  - NuGet publishing pipeline
  - PR validation workflow
  - Custom workflow combining multiple actions
- Comprehensive documentation
  - Main README with usage examples
  - Quick reference guide
  - Best practices and patterns
- Default .NET version set to 10.0.x
- Cross-platform support (Linux, Windows, macOS)
- Code coverage collection and reporting
- Test result publishing with annotations
- NuGet package caching for faster builds

### Features
- ? Modular composite actions for flexible workflow composition
- ? Reusable workflows for common CI/CD patterns
- ? Sensible defaults with easy customization
- ? Cross-platform build support
- ? Security vulnerability scanning
- ? Code quality validation
- ? PR automation capabilities
- ? Comprehensive documentation and examples

### Notes
- Based on Azure DevOps template library patterns
- Designed for .NET 10.0 projects with backward compatibility
- All actions include proper input validation and error handling
- Workflows support both public and private repositories
- Compatible with GitHub Enterprise Server

## [Unreleased]

### Changed
- `docs/consumer-usage.md`: documented ADR-0012 D5/D9 caller-permissions baselines and refreshed reusable-workflow examples so callers declare the load-bearing `permissions:` blocks required by invariant 39.

### Internal

- Enabled ADR-0044 OpenClaw/Codex Grid Review Runner request generation for Actions PRs.

### Added
- `pr-core.yml`: ADR-0044 `authorship-check`, ADR-0011/ADR-0044 `pr-metadata-check`, and warnings-only `pr-size-check` jobs. Authorship now requires a parseable `Authorship:` PR-body line; agent/mixed PRs must declare packet metadata or an explicit out-of-band reason; non-`human` PRs get visible size discipline without blocking Phase 2 merges.
- `.github/config/labels.json`, `seed-labels.yml`, and `seed-labels-fanout.yml`: labels-as-code and idempotent fan-out for `large-pr`, `audit-sample`, `out-of-band`, and `skip-review`.
- `.github/pull_request_template.md`: local PR-body placeholders for ADR-0044 `Authorship:`, `Packet:`, `Out-of-band reason:`, and `Size justification:` fields.
- `docs/consumer-usage.md`: documented ADR-0044 authorship declarations, size-discipline thresholds, missing-config behavior, PR template guidance, and label seeding.
- `job-review-request.yml`: ADR-0044 advisory trigger rail for the OpenClaw/Codex Grid Review Runner. It applies draft/`skip-review`/`.honeydrunk-review.yaml enabled` gates, emits the versioned review-request payload with `owner/repo#pr@headSha` idempotency, signs webhook delivery with timestamped HMAC, and preserves artifact/comment fallback for OpenClaw replay without invoking any model API from GitHub Actions.
- `docs/consumer-usage.md`: documented the Grid Review Request workflow, caller permissions/secrets, `.honeydrunk-review.yaml` opt-in config, skip behavior, and advisory fallback posture.
- `pr-core.yml`: blocking coverage gate for test-bearing repos with patch coverage threshold, no-regress baseline, absolute coverage floor, visible no-test skip, and default-branch baseline ratchet.
- `pr/generate-summary`: Coverage Gate and non-blocking outdated package summary blocks.
- `nightly-deps.yml`: maintains a single `📦 Outdated Dependencies` issue per repo, updated in place and auto-closed when dependencies are current.

- Azure Container Registry login composite action (`azure/acr-login`)
  - Service principal and admin/token authentication modes
  - Input validation with clear error messages
- Azure App Service container deployment composite action (`azure/deploy-app-service`)
  - Deployment slot support with swap-to-production
  - Health check probing with configurable timeout
  - Container startup wait period
  - Outputs: deployed URL and deployment status
- Azure Key Vault secret fetch composite action (`azure/keyvault-fetch`)
  - Fetch secrets by name and expose as environment variables or step outputs
  - Token substitution in config files (e.g., appsettings.json)
  - Automatic value masking in logs
- Reusable deploy container workflow (`job-deploy-container.yml`)
  - Chains ACR login → Key Vault fetch → App Service config → deploy → health check → slot swap
  - Deployment summary in GitHub Step Summary
  - Supports both service principal and admin credentials
- Reusable Azure Container Apps deployment workflow (`job-deploy-container-app.yml`)
  - Optionally builds and pushes images to ACR, or deploys a prebuilt image reference
  - Validates ADR-0015 Container App naming, system-assigned identity, and Multiple revision mode
  - Creates a new revision, health-probes it, and shifts traffic with `full`, `hold`, or `canary:N` modes
  - Configures runtime secrets as Key Vault-backed Container App secret references without fetching secret values into workflow logs
- Azure Container Apps revision deployment composite action (`azure/deploy-container-app`)
  - Uses `az containerapp revision copy` and polls until the new revision reaches Running
  - Outputs revision name and revision FQDN for downstream health checks and summaries
- Consumer example workflow (`examples/deploy-container-app.yml`) for Container Apps build-and-deploy usage
- Consumer usage docs for `job-deploy-container-app.yml`, including inputs, outputs, secrets, traffic modes, and target prerequisites
- Slack/Teams notification composite action (`common/send-notification`)
  - Incoming webhook support for Slack and Teams
  - Configurable status, title, message, and fields
  - Color-coded messages based on workflow status
- Secret scanning (`job-secret-scan.yml`) — replaced stub with gitleaks-action@v2
  - SARIF output uploaded to GitHub Security tab
  - Finding count evaluation with conditional failure
- Coverage analysis (`job-coverage-analysis.yml`) — replaced stub with ReportGenerator
  - Cobertura input → HTML + Markdown + JSON output
  - Configurable coverage threshold with pass/fail
  - GitHub Step Summary with per-assembly breakdown
- Container scanning in release workflow — replaced stub with Trivy
  - `aquasecurity/trivy-action@0.28.0` scans built container images
  - SARIF output uploaded to GitHub Security tab
- SBOM generation in release workflow — replaced stub with anchore/sbom-action
  - SPDX-format software bill of materials attached as artifact
- License compliance in release workflow — replaced stub with dotnet-project-licenses
  - Allow-list based license checking with configurable approved licenses
- Smoke tests in release workflow — replaced stub with real health probing
  - Curl-based endpoint polling with configurable timeout and retry interval
- Nightly security workflow (`nightly-security.yml`) — replaced all stubs
  - SAST: GitHub CodeQL (`github/codeql-action`) with `security-and-quality` queries
  - Secret scan: gitleaks full-history scan with SARIF upload
  - IaC scan: Trivy filesystem misconfig scanning for Terraform, Docker, K8s, Bicep
  - Dependency scan: real `dotnet list package --vulnerable --include-transitive` JSON output
  - Consolidated report: automated finding counts from all SARIF/JSON artifacts
  - GitHub issue creation: auto-create or update issues labeled `security,automated`
  - Rich GitHub Step Summary with scanner breakdown table
- Refresh Hive project metadata workflow (`refresh-hive-project-metadata.yml`) for weekly and manual cache refresh.
- Hive project metadata cache (`.github/config/hive-project-metadata.json`) for stable project, field, and option IDs.

### Changed

- `docs/consumer-usage.md`: documented coverage-gate inputs, `.github/coverage-baseline.json`, default-branch push wiring, and dependency issue permissions.
- `job-coverage-analysis.yml`: marked as superseded by the PR summary coverage gate while retaining the reusable entrypoint.
- `hive-field-mirror.yml`: accept `app-id` and `app-private-key` for GitHub App auth; PAT auth remains available as a fallback.
- `hive-field-mirror.yml`: load cached Hive project metadata before per-issue mirror runs, falling back to live GraphQL lookup when the cache is absent, invalid, or stale.

### Planned
- Integration with SonarQube
- Database deployment actions
- Terraform deployment actions
- Multi-repository support
- Custom labeling and tagging
- Release notes generation
- API compatibility checking (`job-api-compatibility.yml`)

---

For migration guides and breaking changes, see [MIGRATION.md](MIGRATION.md) (when applicable).
