# Copilot Instructions - HoneyDrunk.Actions

You are working in the **HoneyDrunk.Actions** repo.

This repo is the **central library of reusable GitHub Actions workflows and composite actions for the HoneyDrunk Grid**.  
It does not contain application code. It defines **CI rituals** that other repos reuse.

## Core principles

1. **Reusable, not bespoke**  
   - Prefer reusable workflows and composite actions that other repos can `uses:`.  
   - Avoid embedding repo-specific logic or hard coded paths for a single consumer.

2. **Separation of concerns**  
   - This repo orchestrates CI behavior and schedules.  
   - Heavy scanning logic and CLIs belong in other nodes, for example HoneyDrunk.Tools.  
   - Actions should call external tools, not reimplement scanners in YAML.

3. **Fast PRs, deep scheduled checks**  
   - PR workflows must be fast and minimal, only what is directly relevant to the diff.  
   - Slow, broad, or organization wide checks run on schedules, not on every PR.

4. **Convention over configuration**  
   - Use consistent workflow names and layouts.  
   - Prefer a small set of standard rituals over many one off workflows.

5. **Versioned contracts**  
   - Workflows are reusable contracts. Changing behavior in a breaking way should bump the workflow version.  
   - Avoid silently changing semantics for existing consumers.

## Workflow families

Design everything around these families of workflows:

### 1. PR workflows

These run on `pull_request` and are meant to be used as required checks.

- `pr-core.yml`  
  - Target: most repos.  
  - Responsibilities:  
    - Build and unit tests for the repo or solution.  
    - Apply HoneyDrunk.Standards and analyzers.  
    - Run a fast static analysis pass.  
    - Perform secret scanning on the diff only.  
    - Optionally run a fast accessibility check against a limited surface if configured.  
  - Non goals: deep security scans, full site crawls, org wide checks.

- `pr-sdk.yml`  
  - Target: SDK style repos that expose public APIs.  
  - Extends `pr-core` behavior.  
  - Additional responsibilities:  
    - Check public API surface for breaking changes.  
    - Report code coverage and coverage deltas.  

When adding new PR workflows, first ask:  
- Can this be expressed as a variation or extension of `pr-core` or `pr-sdk`  
Only create new PR workflow families if the behavior truly cannot fit those two.

### 2. Release workflows

These run on tags or release branches and may be slower and stricter.

- `release.yml`  
  - Trigger: `push` on version tags, for example `v*`.  
  - Responsibilities:  
    - Build and full test suite.  
    - Generate SBOM (software bill of materials).  
    - Run dependency vulnerability scan.  
    - Run license compliance checks.  
    - Build container images where relevant and run container security scans.  
    - Optionally trigger smoke tests against a deploy slot or test environment.

Release workflows should treat the artifact as shippable and perform all checks that are too expensive for PRs but critical for shipping.

### 3. Scheduled workflows

These workflows are intended to run on a **cron schedule**, not on PRs. They are allowed to be slower and more thorough.

- `nightly-security.yml`  
  - Responsibilities:  
    - Run deeper SAST and security scanning for the repo.  
    - Run full dependency vulnerability scan.  
    - Run infrastructure as code security checks if the repo contains IaC files.  
  - Output: reports or artifacts that can be consumed by other nodes or used to open issues.

- `nightly-deps.yml`  
  - Responsibilities:  
    - Detect outdated dependencies for the repo (NuGet, npm, etc).  
    - Either open or update dependency upgrade pull requests, or produce a machine readable report.  
  - Do not block merges. This is maintenance and visibility.

- `nightly-accessibility.yml`  
  - Target: web or UI repos only. Make this opt in.  
  - Responsibilities:  
    - Build the site or Storybook.  
    - Run a full accessibility scan across configured routes or stories.  
    - Emit a report artifact and, optionally, create or update a tracking issue when violations exceed a threshold.

- `weekly-governance.yml`  
  - This is usually run from a dedicated meta repo.  
  - Responsibilities:  
    - Use GitHub APIs to inspect repos across the org.  
    - Detect repos with no CI.  
    - Detect repos not using required workflows, for example `pr-core`.  
    - Detect repos missing basic governance files such as CODEOWNERS.  
  - Output: a consolidated report and optional issues for problematic repos.

### 4. Manual workflows

- Manual workflows are triggered by `workflow_dispatch`.  
- Use them for on demand heavy runs such as performance profiling, chaos tests, or targeted deep scans.  
- Do not make them part of normal PR or release flows.

## Integration with other nodes

When you need scanning logic, prefer calling tools from other nodes:

- Use **HoneyDrunk.Tools** for CLIs that:  
  - scan dependencies and emit JSON reports  
  - run accessibility checks  
  - run security or license scans  

Actions workflows should shell out to these tools instead of hard coding logic.

If you are about to embed complex scanning behavior inside YAML, step back and consider moving it into HoneyDrunk.Tools or another appropriate node.

## How Copilot should behave in this repo

- When asked to create a new workflow, first propose using or extending an existing workflow family (`pr-core`, `pr-sdk`, `release`, `nightly-security`, `nightly-deps`, `nightly-accessibility`, `weekly-governance`).  
- Prefer small, composable composite actions for repeated step patterns.  
- Keep consumer repo workflows as thin wrappers that call reusable workflows from this repo.  
- Do not add business or application specific logic here.  
- If a request clearly belongs in another node (for example implementing a scanner CLI), suggest creating a work item for that node instead of writing it here.
