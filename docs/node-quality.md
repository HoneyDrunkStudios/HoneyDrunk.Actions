# Node, TypeScript, and RN-web validation

Use [`job-node-workspace.yml`](../.github/workflows/job-node-workspace.yml) for
Node consumers. This extends the existing contract; it does not change the .NET
`pr-core`, `pr-sdk`, build/test, release, or security workflow defaults.
HoneyDrunk.Actions owns this CI boundary. HoneyDrunk.Pipelines is deprecated.

## Consumer contract

Existing defaults remain: `runs-on: ubuntu-latest`, `working-directory: .`,
`node-version: '22'`, `node-version-file: ''`, `package-manager: npm`,
`cache-dependency-path: package-lock.json`, `install-command: npm ci`,
`build-command: npm run build`, `test-command: npm test`, and
`lint-command: npm run lint`. `run-build`, `run-test`, and `run-lint` remain true.
Install, build, test, and lint retain their order and fail-fast behavior.

| Additional input | Default | Contract |
| --- | --- | --- |
| `package-manager-version` | empty | Optional exact stable version installed under `RUNNER_TEMP`, before cache restore. Supports npm, pnpm, and Yarn Classic 1.x; modern Yarn uses a checked-in `yarnPath`. Empty uses the manager available on the runner. |
| `run-typecheck` | `false` | Run the separate typecheck step after lint. |
| `typecheck-command` | `npm run typecheck` | Required, nonblank command when enabled. |
| `browser-install-command` | empty | Optional browser/tool preparation before a11y/E2E. Requires at least one browser check. Use project-pinned tools; no global browser-test package install. |
| `accessibility-command` | empty | Nonblank enables the accessibility check; a nonzero exit fails the job. |
| `e2e-command` | empty | Nonblank enables browser E2E; a nonzero exit fails the job. |
| `coverage-path` | empty | One report file or directory below the workdir; requires `run-test`. |
| `test-results-path` | empty | One report file or directory below the workdir, such as `reports` or `test-results`. |
| `artifact-name` | `node-workspace` | 1–100 letters/digits/dots/underscores/hyphens, beginning with a letter/digit. A descriptive prefix helps identify each call/matrix entry. Run ID, attempt, and a unique invocation suffix are appended to prevent collisions even with unchanged caller defaults. |
| `upload-summary-artifact` | `false` | Opt into a JSON-only artifact when neither report path is configured. A requested coverage/test report always enables upload, including the JSON summary. |
| `artifact-retention-days` | `14` | Integer 1–90, subject to the repository's retention policy. |
| `timeout-minutes` | `360` | Integer 1–360. Preserves the previous inherited timeout; callers should set 20 for fast checks or an appropriate bounded heavy-suite budget. |

Paths use forward slashes. The workdir is relative to the caller's checkout;
`cache-dependency-path` and `node-version-file` resolve from that workdir and may
use `..` to reach shared monorepo files inside `GITHUB_WORKSPACE`. For example,
`working-directory: packages/web` accepts `cache-dependency-path: ../../package-lock.json`
and `node-version-file: ../../.nvmrc`. Resolved paths and glob matches must stay
inside the checkout, including through symlinks. Absolute paths, drive prefixes,
backslashes, control characters, and checkout escapes are rejected as explicit
input hardening; migrate absolute paths to relative paths when adopting this
revision. The cache input accepts newline-separated relative lockfiles/globs.
New evidence paths are confined to the workdir: no parent traversal, glob, workdir root,
hidden path, or symlink. Requested evidence that is missing or has no nonempty files fails the
job even if its test command returned zero. Hidden files are excluded. Coverage
and test reports are copied into a temporary artifact directory before upload.

The job always attempts a step summary and local `validation-results.json`, including after
command failure. It records each command's `requested` flag and actual step
`outcome`: `success`, `failure`, `skipped`, or `cancelled`. Skipped checks say
whether they were disabled or blocked before execution. Artifact upload runs only
when a report path is requested or `upload-summary-artifact: true`; unchanged
callers do not acquire an artifact-service dependency. Enabled uploads include
the JSON summary and validated report snapshots; the original test failure remains fatal.
Hard runner loss or job termination can prevent this best-effort upload.

Reusable outputs are `test-result`, `typecheck-result`, `accessibility-result`,
and `e2e-result`. A successful command is not proof that a framework discovered
tests: consumer configs must reject zero tests and enforce their actual coverage
thresholds. This workflow does not invent thresholds, parse LCOV into a quality
claim, or turn skipped native testing into a pass. Overall job failure remains
authoritative if setup, build, reports, or upload failed.

## Fast PR and heavier gates

[`examples/node-quality.yml`](../examples/node-quality.yml) contains separate
fast PR and manual/tag validation calls, plus the existing Node security audit.
Replace `NODE_QUALITY_COMMIT` with the reviewed, published Actions commit SHA
before enabling a consumer. An unpushed local SHA cannot be resolved by GitHub.
Choose scripts and report paths that actually exist in each app; examples are
contracts, not evidence that either consumer has already passed them.

Fast checks should cover unit/component behavior, failure paths, typecheck, lint,
and build. An in-process accessibility component test can be part of `test-command`.
Heavy browser suites own server startup/readiness/teardown, deterministic seed
data, browser versions, retries, traces, screenshots, and report generation in
the consumer's harness. Prefer the harness's server lifecycle configuration over
background shell processes. Keep local fake-backed browser tests distinct from
deployed-service E2E. Configure failures to return nonzero; do not use
`--passWithNoTests`, `|| true`, or a warning-only accessibility command as a gate.

Concurrency belongs in the caller. Include the workflow identity, PR/ref, and
gate identity where needed. Cancel superseded PR runs; do not cancel an in-flight
release gate. The reusable job deliberately does not reuse `github.workflow` as
its own concurrency group, which could cancel its caller. No schedules, devices,
paid services, or branch protection changes are introduced by this extension.

## Trust, caching, and dependencies

Use `pull_request`, with `contents: read`, no `secrets: inherit`, and no privileged
environment. `pull_request_target` is rejected before checkout. Checkout does not
persist credentials. Treat every command input as caller-authored Bash code;
never construct a command from PR titles, bodies, branch names, or other event
data. Commands travel through environment variables and execute in a fresh Bash
process with `-e -o pipefail`. Ordinary path and version inputs are validated as
data, not interpolated into shell source.

Use ephemeral GitHub-hosted runners for untrusted PRs. Retained `runs-on` support
is not permission to expose persistent self-hosted machines to fork code. Custom
runner images need Bash, Python 3.10+, and Node action runtime support. This job
does not accept registry or deployment secrets. Private authenticated package
installation requires a separately reviewed trust design.

The existing setup-node and upload-artifact SHA pins are retained. Setup happens
before manager provisioning and cache restore. Only the package manager's
download cache is restored using lockfile hashes; `node_modules` and reports are
not cached. This follows the [setup-node cache contract](https://github.com/actions/setup-node/tree/a0853c24544627f65ddf259abe73b1d18a591444).
Use immutable installs (`npm ci`, `pnpm install --frozen-lockfile`, or the
corresponding Yarn option). Choosing `package-manager` only chooses the manager
and cache: callers must explicitly change `install-command` and other commands
when using pnpm/Yarn. Monorepos can either use a nested workdir with parent-relative
lockfile/version paths or use the repository root with workspace script selectors.

Reuse [`job-node-security-audit.yml`](../.github/workflows/job-node-security-audit.yml)
as a separate dependency gate. Its nonzero audit status remains fatal and its
JSON report is uploaded after failure. For a single-package app, override its
workspace-oriented default with `npm audit --audit-level=high --json`.
The existing audit still reports all severities while the command determines
which severity blocks. Do not suppress existing unpatched findings, omit dev
dependencies to hide toolchain findings, or append `|| true`.
[`job-node-dependency-report.yml`](../.github/workflows/job-node-dependency-report.yml)
reports outdated packages; it is not a vulnerability gate. These existing jobs
retain their interfaces, cache setup, artifact names, and retention defaults.
Their package manager must already be available on the selected runner; the new
manager provisioning option currently belongs only to Node Workspace.

## Standards and current limits

[ADR-0047](https://github.com/HoneyDrunkStudios/HoneyDrunk.Studio/blob/main/adrs/ADR-0047-testing-patterns-and-tooling.md)
separates fast unit/integration checks from deployed E2E, defines risk-based
coverage targets, and names Maestro for mobile. Its committed web E2E binding is
.NET Playwright. The user-approved Node/TS/RN-web work here supplies a
command-based extension for those consumers; it does not rewrite that ADR or
claim to complete the pending .NET integration/E2E jobs. Test thresholds belong
in reviewed project configuration with measured baselines and meaningful failure,
edge, accessibility, and interaction coverage—not a universal 100% label.

The existing accessibility scan action and nightly workflow are advisory helpers:
the scan installs global unpinned pa11y packages and does not fail for violations.
They remain unchanged to preserve callers. The new accessibility hook allows a
consumer's lockfile-pinned harness to act as a blocking check. Automated axe or
pa11y results do not establish full WCAG compliance. Keyboard, focus, screen
reader, text scaling, reduced motion, and platform-specific interaction testing
remain part of product acceptance.

### Proposed native E2E contract (not implemented)

A future device job should accept `platform` (Android/iOS), an immutable app
artifact identity, `app-id`, a repository-relative Maestro flow directory, an
explicit emulator/simulator profile and OS version, and a bounded timeout. It
must install the supplied build, boot and await the device, run real flows,
preserve JUnit/log/screenshot/video evidence on failure, distinguish unsupported
or skipped runs from passes, and tear down the device/test data. Android needs a
runner with a working emulator and acceleration; iOS needs macOS with a compatible
Xcode/simulator. Signing/build credentials belong to a separate trusted build
boundary. Runner/cost approval and a working consumer flow are prerequisites.
This change provisions none of that. Linux browser checks of RN-web provide no
native Android/iOS E2E evidence.

## Local validation

With Python, Node/npm, Git Bash/Bash, and actionlint available:

```bash
python3 -m venv /tmp/node-workflow-tests
/tmp/node-workflow-tests/bin/python -m pip install -r tests/requirements.txt
/tmp/node-workflow-tests/bin/python -m unittest discover -s tests -p 'test_node_workspace.py' -v
actionlint -shellcheck=
```

The suite parses the real YAML, executes its validator/report scripts, and runs
its Bash command steps in a temporary npm consumer without registry dependencies.
It covers defaults, outcomes, failure propagation, quoting, parent-relative
monorepo paths, missing reports, and symlink escapes. Existing regressions still
run in `actions-ci.yml`. That workflow also calls this exact reusable-workflow
revision against a dependency-free nested npm fixture with the default manager
and an explicit npm version. A follow-on job downloads and validates the real
artifacts, JUnit results, command outcomes, and Node/npm versions, covering
setup-node, cache setup, temporary-manager PATH propagation, and the artifact
service. Downloads are scoped to the current run attempt so reruns cannot use
stale evidence. A rerun can additionally verify cache-hit restoration in the
hosted step logs. This fixture does not attest app/browser or native behavior.
pnpm/Yarn provisioning, Windows/macOS hosted images, actual app harnesses, and
native device flows still require their own execution evidence.
