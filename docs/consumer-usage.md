# Consumer Usage Guide

This document provides sample workflows for consuming repos to adopt the HoneyDrunk.Actions workflow families.

## Table of Contents

- [PR Core Workflow](#pr-core-workflow)
- [PR SDK Workflow](#pr-sdk-workflow)
- [Release Workflow](#release-workflow)
- [Nightly Security Workflow](#nightly-security-workflow)
- [Nightly Dependencies Workflow](#nightly-dependencies-workflow)
- [Nightly Accessibility Workflow](#nightly-accessibility-workflow)
- [Weekly Governance Workflow](#weekly-governance-workflow)

---

## PR Core Workflow

**Purpose:** Fast PR validation for most repos. Required check that provides quick feedback.

**When to Use:** All repos that need basic CI validation (build, test, standards).

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

### Full Example with Options

```yaml
name: PR Validation

on:
  pull_request:
    branches: [main, develop]

jobs:
  pr-validation:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/pr-core.yml@main
    with:
      dotnet-version: '10.0.x'
      configuration: 'Release'
      runs-on: 'ubuntu-latest'
      working-directory: '.'
      project-path: './src/MyProject.sln'
      enable-secret-scan: true
      enable-accessibility-check: false
      post-pr-summary: true
      actions-ref: 'main'
    secrets:
      github-token: ${{ secrets.GITHUB_TOKEN }}

permissions:
  contents: read
  checks: write
  pull-requests: write
```

### Web App with Accessibility Check

```yaml
name: PR Validation

on:
  pull_request:
    branches: [main]

jobs:
  pr-validation:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/pr-core.yml@main
    with:
      enable-accessibility-check: true
      accessibility-url: 'http://localhost:5000'
    secrets:
      github-token: ${{ secrets.GITHUB_TOKEN }}

permissions:
  contents: read
  checks: write
  pull-requests: write
```

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

jobs:
  pr-sdk-validation:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/pr-sdk.yml@main
    secrets:
      github-token: ${{ secrets.GITHUB_TOKEN }}

permissions:
  contents: read
  checks: write
  pull-requests: write
```

### Full Example with Coverage and API Baseline

```yaml
name: PR SDK Validation

on:
  pull_request:
    branches: [main, develop]

jobs:
  pr-sdk-validation:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/pr-sdk.yml@main
    with:
      dotnet-version: '10.0.x'
      configuration: 'Release'
      project-path: './src/MyLibrary/MyLibrary.csproj'
      api-compat-baseline: './api-baseline.txt'
      coverage-threshold: 80
      coverage-delta-threshold: 5
      enable-secret-scan: true
      post-pr-summary: true
    secrets:
      github-token: ${{ secrets.GITHUB_TOKEN }}

permissions:
  contents: read
  checks: write
  pull-requests: write
```

---

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

jobs:
  release:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/release.yml@main
    with:
      enable-nuget-publish: true
      nuget-source: 'https://api.nuget.org/v3/index.json'
    secrets:
      nuget-api-key: ${{ secrets.NUGET_API_KEY }}

permissions:
  contents: read
  packages: write
  id-token: write
```

### Container Application Release

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
      enable-container-build: true
      dockerfile-path: './Dockerfile'
      container-registry: 'ghcr.io'
      container-image-name: 'honeydrunkstudios/my-app'
      enable-smoke-tests: true
      smoke-test-url: 'https://staging.myapp.com/health'
    secrets:
      container-registry-username: ${{ github.actor }}
      container-registry-password: ${{ secrets.GITHUB_TOKEN }}

permissions:
  contents: read
  packages: write
  id-token: write
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
  contents: read
  packages: write
  id-token: write
```

---

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
  contents: read
  security-events: write
  issues: write
```

---

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
```

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
```

---

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

permissions:
  contents: write
  checks: write
  pull-requests: write
  packages: write
  security-events: write
  issues: write
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
         - uses: actions/checkout@v4
         - name: Setup .NET
           uses: actions/setup-dotnet@v4
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

## Support

For questions, issues, or feature requests:
- **Repository:** https://github.com/HoneyDrunkStudios/HoneyDrunk.Actions
- **Issues:** https://github.com/HoneyDrunkStudios/HoneyDrunk.Actions/issues
- **Documentation:** This file and workflow headers
