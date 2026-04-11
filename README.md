# HoneyDrunk.Actions

Central library of reusable GitHub Actions workflows and composite actions for the HoneyDrunk Grid.

## 📚 Table of Contents

- [Overview](#overview)
- [Workflow Families](#workflow-families)
- [Quick Start](#quick-start)
- [Composite Actions](#composite-actions-steps)
- [Legacy Workflows](#legacy-workflows)
- [Documentation](#documentation)
- [Design Principles](#design-principles)
- [Contributing](#contributing)
- [Additional Resources](#additional-resources)

## 🎯 Overview

HoneyDrunk.Actions provides standardized CI/CD workflows that can be reused across all repositories in the HoneyDrunk ecosystem. This ensures consistency, reduces duplication, and simplifies maintenance.

### Key Features

✅ **Workflow Families** - Standard rituals for PR, release, security, dependencies, accessibility, and governance  
✅ **Fast PR Validation** - Minimal checks for quick feedback  
✅ **Deep Scheduled Scans** - Comprehensive analysis without blocking development  
✅ **.NET 10.0 Support** - Latest .NET with easy version customization  
✅ **Cross-Platform** - Linux, Windows, macOS support  
✅ **Composite Actions** - Reusable scanning and deployment actions  
✅ **Versioned Contracts** - Semantic versioning for stability  

## 🏗️ Workflow Families

### PR Workflows

Fast validation for pull requests:

- **[pr-core.yml](.github/workflows/pr-core.yml)** - Basic PR validation for most repos
  - Build and unit tests
  - Fast static analysis
  - Diff-only secret scanning
  - Optional minimal accessibility check
  
- **[pr-sdk.yml](.github/workflows/pr-sdk.yml)** - Extended validation for SDK repos
  - Everything in pr-core
  - API compatibility checks
  - Code coverage with delta reporting
  - Documentation completeness validation

### Release Workflows

Comprehensive release validation:

- **[release.yml](.github/workflows/release.yml)** - Production release workflow
  - Full test suite
  - SBOM generation
  - Dependency vulnerability scan
  - License compliance checks
  - Container build and scan (optional)
  - Smoke tests (optional)

### Scheduled Workflows

Deep analysis on a schedule:

- **[nightly-security.yml](.github/workflows/nightly-security.yml)** - Comprehensive security scanning
  - Deep SAST analysis
  - Full dependency vulnerability scan
  - Infrastructure as Code security checks
  - Secret scanning across entire codebase

- **[nightly-deps.yml](.github/workflows/nightly-deps.yml)** - Dependency management
  - Detect outdated NuGet and npm packages
  - Check for deprecated packages
  - Auto-generate dependency update PRs (optional)

- **[nightly-accessibility.yml](.github/workflows/nightly-accessibility.yml)** - Accessibility compliance
  - Build and serve web apps/Storybook
  - Full WCAG 2.1 AA/AAA scanning
  - Track violations with GitHub issues

- **[weekly-governance.yml](.github/workflows/weekly-governance.yml)** - Organization governance
  - Scan repos for CI workflow presence
  - Check for required workflows and files
  - Detect stale branches and PRs
  - Ensure security policies exist

## 🚀 Quick Start

### Basic PR Workflow

Add to your repo at `.github/workflows/pr.yml`:

```yaml
name: PR Validation

on:
  pull_request:
    branches: [main]

jobs:
  pr-validation:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/pr-core.yml@main
    secrets:
      github-token: ${{ secrets.GITHUB_TOKEN }}

permissions:
  contents: read
  checks: write
  pull-requests: write
```

### SDK/Library PR Workflow

For repos with public APIs:

```yaml
name: PR SDK Validation

on:
  pull_request:
    branches: [main]

jobs:
  pr-sdk-validation:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/pr-sdk.yml@main
    with:
      coverage-threshold: 80
    secrets:
      github-token: ${{ secrets.GITHUB_TOKEN }}

permissions:
  contents: read
  checks: write
  pull-requests: write
```

### Release Workflow

For tag-based releases:

```yaml
name: Release

on:
  push:
    tags:
      - 'v*'

jobs:
  release:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/release.yml@main
    with:
      enable-nuget-publish: true
    secrets:
      nuget-api-key: ${{ secrets.NUGET_API_KEY }}

permissions:
  contents: read
  packages: write
  id-token: write
```

### Nightly Security Scan

```yaml
name: Nightly Security

on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM UTC daily

jobs:
  security-scan:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/nightly-security.yml@main
    secrets:
      github-token: ${{ secrets.GITHUB_TOKEN }}

permissions:
  contents: read
  security-events: write
  issues: write
```

## 📖 Documentation

- **[Consumer Usage Guide](docs/consumer-usage.md)** - Complete examples for all workflows
- **Workflow Headers** - Each workflow contains detailed inline documentation
- **[Quick Reference](docs/QUICK-REFERENCE.md)** - Common patterns and troubleshooting

## 🧩 Composite Actions (Steps)

### .NET Actions

#### Setup .NET SDK
Installs a specific version of the .NET SDK.

```yaml
- uses: ./.github/actions/dotnet/setup
  with:
    dotnet-version: '10.0.x'  # Default: 10.0.x
    include-prerelease: false  # Default: false
```

#### Restore Dependencies
Restores NuGet packages for .NET projects.

```yaml
- uses: ./.github/actions/dotnet/restore
  with:
    working-directory: '.'     # Default: .
    verbosity: 'minimal'       # Default: minimal
```

#### Build Project
Builds a .NET project or solution.

```yaml
- uses: ./.github/actions/dotnet/build
  with:
    project-path: '.'          # Default: .
    configuration: 'Release'   # Default: Release
    no-restore: false          # Default: false
    working-directory: '.'     # Default: .
```

#### Test Project
Runs tests with coverage and result reporting.

```yaml
- uses: ./.github/actions/dotnet/test
  with:
    configuration: 'Release'              # Default: Release
    no-build: false                       # Default: false
    test-results-directory: 'TestResults' # Default: TestResults
    collect-coverage: true                # Default: true
    working-directory: '.'                # Default: .
```

#### Pack Project
Creates NuGet packages.

```yaml
- uses: ./.github/actions/dotnet/pack
  with:
    project-path: '.'          # Default: .
    configuration: 'Release'   # Default: Release
    output-directory: './artifacts'  # Default: ./artifacts
    version-suffix: ''         # Default: empty
    no-build: false            # Default: false
    working-directory: '.'     # Default: .
```

#### Publish Application
Publishes a .NET application for deployment.

```yaml
- uses: ./.github/actions/dotnet/publish
  with:
    project-path: '.'          # Default: .
    configuration: 'Release'   # Default: Release
    output-directory: './publish'  # Default: ./publish
    runtime: ''                # Default: empty (portable)
    self-contained: false      # Default: false
    no-build: false            # Default: false
    working-directory: '.'     # Default: .
```

### NuGet Actions

#### Setup NuGet Cache
Configures caching for NuGet packages.

```yaml
- uses: ./.github/actions/nuget/setup-cache
  with:
    cache-key-prefix: 'nuget'  # Default: nuget
    working-directory: '.'     # Default: .
```

#### Push NuGet Package
Pushes packages to a NuGet feed.

```yaml
- uses: ./.github/actions/nuget/push
  with:
    package-path: '*.nupkg'    # Required
    source: 'https://api.nuget.org/v3/index.json'  # Default
    api-key: ${{ secrets.NUGET_API_KEY }}  # Required
    skip-duplicate: true       # Default: true
```

#### Add NuGet Source
Adds a custom NuGet source.

```yaml
- uses: ./.github/actions/nuget/add-source
  with:
    source-name: 'MyFeed'      # Required
    source-url: 'https://...'  # Required
    username: ''               # Optional
    password: ''               # Optional
```

### Diagnostics Actions

#### Debug Build Identity
Displays environment information for debugging.

```yaml
- uses: ./.github/actions/diagnostics/debug-build-identity
```

#### Validate Test Naming
Checks test file naming conventions.

```yaml
- uses: ./.github/actions/diagnostics/validate-test-naming
  with:
    test-directory: '.'        # Default: .
    pattern: '.*Tests?\.cs$'   # Default: .*Tests?\.cs$
```

#### Publish Test Results
Uploads and publishes test results with annotations.

```yaml
- uses: ./.github/actions/diagnostics/publish-test-results
  with:
    test-results-directory: 'TestResults'  # Default: TestResults
    report-name: 'Test Results'  # Default: Test Results
```

### Security Actions

#### Vulnerability Scan
Scans for known security vulnerabilities.

```yaml
- uses: ./.github/actions/security/vulnerability-scan
  with:
    working-directory: '.'     # Default: .
    fail-on-severity: 'moderate'  # Default: moderate
    # Options: low, moderate, high, critical
```

### PR Actions

#### Generate PR Summary
Generates a build summary for pull requests.

```yaml
- uses: ./.github/actions/pr/generate-summary
  with:
    include-coverage: true     # Default: true
    test-results-directory: 'TestResults'  # Default: TestResults
```

#### Post PR Comment
Posts a comment to the pull request.

```yaml
- uses: ./.github/actions/pr/post-comment
  with:
    github-token: ${{ secrets.GITHUB_TOKEN }}  # Required
    message: 'Build successful!'  # Required
    comment-tag: 'build-bot'   # Default: build-bot
```

## 🔄 Legacy Workflows

The repository also contains legacy template-based workflows for backward compatibility:

### Legacy PR Validation

**Path:** `.github/workflows/legacy/pr-validation.yml`

```yaml
name: Legacy PR Validation

on:
  pull_request:
    branches: [main]

jobs:
  validate:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/legacy/pr-validation.yml@main
    secrets:
      github-token: ${{ secrets.GITHUB_TOKEN }}

permissions:
  contents: read
  checks: write
  pull-requests: write
```

### Legacy Release

**Path:** `.github/workflows/legacy/release.yml`

```yaml
name: Legacy Release

on:
  push:
    tags:
      - 'v*'

jobs:
  release:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/legacy/release.yml@main
    with:
      enable-nuget-publish: true
    secrets:
      nuget-api-key: ${{ secrets.NUGET_API_KEY }}

permissions:
  contents: read
  packages: write
  id-token: write
```

## 🎯 Design Principles

### 1. Reusable, Not Bespoke
All workflows are designed to be consumed via `uses:` syntax. No repo-specific logic.

### 2. Separation of Concerns
This repo orchestrates CI behavior. Complex scanning logic is extracted into composite actions under `.github/actions/`.

### 3. Fast PRs, Deep Scheduled Checks
- PR workflows: Fast and minimal, only relevant to the diff
- Scheduled workflows: Slow, thorough, organization-wide

### 4. Convention Over Configuration
Consistent workflow names and minimal configuration required.

### 5. Versioned Contracts
Breaking changes bump workflow versions. Semantic versioning for stability.

## 🔧 Composite Actions

Scanning and deployment logic is implemented as composite actions under `.github/actions/`. Workflows call these actions instead of embedding complex logic inline:

- Dependency scanning and reporting
- SAST analysis
- Accessibility testing
- API compatibility checking
- SBOM generation
- Governance checks

Some of these are still being implemented. Placeholder steps in workflows will be replaced as composite actions are built out.

## 📝 Versioning

### For Consumers

Pin to stable versions for production:

```yaml
uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/pr-core.yml@v1.0.0
```

Or use `@main` for latest features (less stable):

```yaml
uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/pr-core.yml@main
```

### For Contributors

- Major version: Breaking changes to workflow inputs/outputs
- Minor version: New features, backward compatible
- Patch version: Bug fixes

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### Adding New Actions

1. Create a new directory under `.github/actions/`
2. Add an `action.yml` file with proper inputs and outputs
3. Test the action in a sample workflow
4. Update this README with documentation
5. Add an example to the `examples/` directory

### Guidelines

- Follow the existing naming conventions
- Use composite actions for shell-based operations
- Provide sensible defaults for all inputs
- Document all inputs and outputs clearly
- Include examples in the action documentation
- Maintain the three-tier hierarchy

## 📝 License

This project is licensed under the terms specified in the [LICENSE](LICENSE) file.

## 📚 Additional Resources

- **[Quick Reference](docs/QUICK-REFERENCE.md)** - Common patterns and troubleshooting
- **[Examples](examples/)** - Ready-to-use workflow examples
- **[Azure DevOps Examples](devops-example/examples/)** - Azure Pipelines examples
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Azure Pipelines Documentation](https://docs.microsoft.com/en-us/azure/devops/pipelines/)
- [.NET CLI Documentation](https://docs.microsoft.com/en-us/dotnet/core/tools/)

---

**HoneyDrunk Studios** - Building better CI/CD pipelines, one action at a time.

## 🐝 The Hive Field Mirror (ADR-0008 D4)

`hive-field-mirror.yml` is a reusable workflow that mirrors issue labels into custom fields on **The Hive** (GitHub Project v2 #4).

### What it updates

| Source | Project field | Behavior |
| --- | --- | --- |
| `wave-1`, `wave-2`, `wave-3` | `Wave` (single select) | Maps to `Wave 1`, `Wave 2`, `Wave 3`; if none present sets `N/A`. |
| `adr-####` labels | `ADR` (text) | Writes uppercase, comma-separated labels (example: `ADR-0005, ADR-0008`). |
| `tier-1`, `tier-2`, `tier-3` | `Tier` (single select) | Direct mapping when present. If absent, the workflow leaves Tier unchanged. |
| Repository name | `Node` (single select) | Uses `.github/config/repo-to-node.yml` lookup. |
| `initiative-<slug>` | `Initiative` (single select) | Optional. Set only when label exists and option exists on the field. |

The workflow intentionally **does not modify `Status`**.

### Reusable workflow contract

Workflow: `.github/workflows/hive-field-mirror.yml`

Inputs:
- `project-owner` (default: `HoneyDrunkStudios`)
- `project-number` (default: `4`)
- `issue-url` (optional override for callers)

Secret:
- `HIVE_FIELD_MIRROR_TOKEN` (or pass as `hive-field-mirror-token` in `workflow_call`)

### Enable in a consuming repo

Add `.github/workflows/hive-mirror.yml`:

```yaml
name: Hive Mirror

on:
  issues:
    types: [opened, labeled, unlabeled, edited]

jobs:
  mirror:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/hive-field-mirror.yml@main
    secrets:
      hive-field-mirror-token: ${{ secrets.HIVE_FIELD_MIRROR_TOKEN }}
```

### Node lookup maintenance

Update `.github/config/repo-to-node.yml` whenever a new repo/node is introduced.

Format:

```yaml
Repository.Name: node-option-slug
```

### Token rotation

1. Create a new fine-grained GitHub App/PAT token with:
   - Issues read access on target repos.
   - Organization Projects write access on `HoneyDrunkStudios`.
2. Replace org secret `HIVE_FIELD_MIRROR_TOKEN`.
3. Trigger the mirror workflow on a test issue to verify updates.
4. Revoke old token.

### One-off backfill

Use `scripts/hive-backfill-issue.sh` to mirror one issue manually:

```bash
HIVE_FIELD_MIRROR_TOKEN=*** ./scripts/hive-backfill-issue.sh --url https://github.com/HoneyDrunkStudios/HoneyDrunk.Actions/issues/123
```
