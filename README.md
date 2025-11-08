# HoneyDrunk.Actions

GitHub Actions reusable workflows and composite actions — the public CI/CD toolkit for open-source and community-facing HoneyDrunk projects.

## 📚 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Directory Structure](#directory-structure)
- [Composite Actions (Steps)](#composite-actions-steps)
- [Job-Level Workflows](#job-level-workflows)
- [Stage-Level Workflows](#stage-level-workflows)
- [Examples](#examples)
- [Best Practices](#best-practices)
- [Azure DevOps Templates](#azure-devops-templates)
- [Contributing](#contributing)
- [Additional Resources](#additional-resources)

## 🎯 Overview

This repository contains comprehensive template libraries for both GitHub Actions and Azure DevOps, providing a three-tier architecture that mirrors Azure DevOps patterns:

- **Actions** (Steps): Reusable building blocks for common tasks
- **Jobs**: Single-job workflows for specific operations
- **Stages**: Multi-job workflows for complete CI/CD pipelines

### Key Features

✅ .NET 10.0 support with easy version customization  
✅ Cross-platform builds (Linux, Windows, macOS)  
✅ NuGet package caching for faster builds  
✅ Code coverage collection and reporting  
✅ Security vulnerability scanning  
✅ Test result publishing with annotations  
✅ PR validation and commenting  
✅ Flexible three-tier composition  

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│  STAGES (Multi-Job Workflows)                           │
│  Complete CI/CD pipelines you drop into your repo       │
│  └─ .github/workflows/templates/stages/                 │
│     ├─ pr-validation.yml                                │
│     ├─ dotnet-library-ci.yml                            │
│     ├─ dotnet-library-release.yml                       │
│     └─ dotnet-app-ci.yml                                │
└─────────────────────────────────────────────────────────┘
                         ↓ composed of
┌─────────────────────────────────────────────────────────┐
│  JOBS (Single-Job Workflows)                            │
│  Opinionated units of work                              │
│  └─ .github/workflows/templates/jobs/                   │
│     ├─ build-and-test.yml                               │
│     ├─ code-quality.yml                                 │
│     └─ publish-nuget.yml                                │
└─────────────────────────────────────────────────────────┘
                         ↓ composed of
┌─────────────────────────────────────────────────────────┐
│  ACTIONS (Composite Actions)                            │
│  Primitive building blocks (steps)                      │
│  └─ .github/actions/                                    │
│     ├─ dotnet/ (setup, restore, build, test...)        │
│     ├─ nuget/ (cache, push, add-source)                │
│     ├─ diagnostics/ (debug, validate, publish)         │
│     ├─ security/ (vulnerability-scan)                   │
│     └─ pr/ (generate-summary, post-comment)            │
└─────────────────────────────────────────────────────────┘
```

### When to Use What

| Level | Use When | Example |
|-------|----------|---------|
| **Stages** | You want a complete pipeline | `dotnet-library-ci.yml` for standard library builds |
| **Jobs** | You need custom composition | Mix `build-and-test` + custom deployment job |
| **Actions** | You need maximum control | Build complex workflows step-by-step |

## 🚀 Quick Start

### Using a Stage (Recommended for most cases)

Create a workflow file in your repository (e.g., `.github/workflows/ci.yml`):

```yaml
name: CI

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  ci:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/templates/stages/dotnet-library-ci.yml@main
    with:
      dotnet-version: '10.0.x'
      configuration: 'Release'
      enable-code-quality: true
```

### Using Jobs (For custom composition)

```yaml
jobs:
  build:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/templates/jobs/build-and-test.yml@main
    with:
      dotnet-version: '10.0.x'
  
  custom-deploy:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - run: echo "Custom deployment logic"
```

### Using Actions (For maximum control)

```yaml
steps:
  - uses: actions/checkout@v4
  
  - name: Setup .NET
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/actions/dotnet/setup@main
    with:
      dotnet-version: '10.0.x'
  
  - name: Build
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/actions/dotnet/build@main
    with:
      configuration: 'Release'
```

## 📁 Directory Structure

```
.github/
├── actions/                    # STEP-LEVEL: Composite actions (primitives)
│   ├── dotnet/                # .NET SDK operations
│   │   ├── setup/
│   │   ├── restore/
│   │   ├── build/
│   │   ├── test/
│   │   ├── pack/
│   │   └── publish/
│   ├── nuget/                 # NuGet operations
│   │   ├── setup-cache/
│   │   ├── push/
│   │   └── add-source/
│   ├── diagnostics/           # Diagnostics & validation
│   │   ├── debug-build-identity/
│   │   ├── validate-test-naming/
│   │   └── publish-test-results/
│   ├── security/              # Security scanning
│   │   └── vulnerability-scan/
│   └── pr/                    # Pull request operations
│       ├── generate-summary/
│       └── post-comment/
└── workflows/
    └── templates/
        ├── jobs/              # JOB-LEVEL: Single-job workflows
        │   ├── build-and-test.yml
        │   ├── code-quality.yml
        │   └── publish-nuget.yml
        └── stages/            # STAGE-LEVEL: Multi-job workflows
            ├── pr-validation.yml
            ├── dotnet-library-ci.yml
            ├── dotnet-library-release.yml
            └── dotnet-app-ci.yml
```

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

## 🔄 Job-Level Workflows

Single-job reusable workflows for specific tasks. These are opinionated units of work that you can compose into custom pipelines.

### Build and Test Job
Complete build and test pipeline with coverage.

**Path:** `.github/workflows/templates/jobs/build-and-test.yml`

```yaml
jobs:
  build:
    uses: ./.github/workflows/templates/jobs/build-and-test.yml
    with:
      dotnet-version: '10.0.x'     # Default: 10.0.x
      configuration: 'Release'      # Default: Release
      runs-on: 'ubuntu-latest'      # Default: ubuntu-latest
      working-directory: '.'        # Default: .
      enable-cache: true            # Default: true
      collect-coverage: true        # Default: true
```

### Code Quality Job
Runs security scans and code quality checks.

**Path:** `.github/workflows/templates/jobs/code-quality.yml`

```yaml
jobs:
  quality:
    uses: ./.github/workflows/templates/jobs/code-quality.yml
    with:
      dotnet-version: '10.0.x'     # Default: 10.0.x
      runs-on: 'ubuntu-latest'      # Default: ubuntu-latest
      working-directory: '.'        # Default: .
      fail-on-severity: 'moderate'  # Default: moderate
      validate-test-naming: true    # Default: true
      check-formatting: true        # Default: true
      fail-on-formatting-issues: false  # Default: false
```

**Formatting Check Options:**
- `check-formatting: true` - Run `dotnet format --verify-no-changes`
- `fail-on-formatting-issues: false` - Warn only (good for gradual adoption)
- `fail-on-formatting-issues: true` - Fail build on formatting issues (HoneyDrunk.Standards alignment)

### Publish NuGet Job
Builds, tests, and publishes NuGet packages.

**Path:** `.github/workflows/templates/jobs/publish-nuget.yml`

```yaml
jobs:
  publish:
    uses: ./.github/workflows/templates/jobs/publish-nuget.yml
    with:
      dotnet-version: '10.0.x'     # Default: 10.0.x
      configuration: 'Release'      # Default: Release
      runs-on: 'ubuntu-latest'      # Default: ubuntu-latest
      project-path: '.'             # Default: .
      nuget-source: 'https://api.nuget.org/v3/index.json'
      skip-duplicate: true          # Default: true
    secrets:
      nuget-api-key: ${{ secrets.NUGET_API_KEY }}
```

## 🎭 Stage-Level Workflows

Multi-job workflows for complete CI/CD pipelines. These are full pipelines you can drop into any repository.

### PR Validation Stage
Complete PR validation with build, test, and code quality checks.

**Path:** `.github/workflows/templates/stages/pr-validation.yml`

```yaml
jobs:
  validate:
    uses: ./.github/workflows/templates/stages/pr-validation.yml
    with:
      dotnet-version: '10.0.x'     # Default: 10.0.x
      configuration: 'Release'      # Default: Release
      runs-on: 'ubuntu-latest'      # Default: ubuntu-latest
      working-directory: '.'        # Default: .
      enable-code-quality: true     # Default: true
      post-pr-comment: false        # Default: false
    secrets:
      github-token: ${{ secrets.GITHUB_TOKEN }}
```

**Includes:** Build + Test + Code Quality + PR Summary

### .NET Library CI Stage
Complete CI pipeline for .NET libraries.

**Path:** `.github/workflows/templates/stages/dotnet-library-ci.yml`

```yaml
jobs:
  ci:
    uses: ./.github/workflows/templates/stages/dotnet-library-ci.yml
    with:
      dotnet-version: '10.0.x'     # Default: 10.0.x
      configuration: 'Release'      # Default: Release
      runs-on: 'ubuntu-latest'      # Default: ubuntu-latest
      working-directory: '.'        # Default: .
      enable-code-quality: true     # Default: true
```

**Includes:** Build + Test + Code Quality

### .NET Library Release Stage
Complete release pipeline for .NET libraries including package publishing.

**Path:** `.github/workflows/templates/stages/dotnet-library-release.yml`

```yaml
jobs:
  release:
    uses: ./.github/workflows/templates/stages/dotnet-library-release.yml
    with:
      dotnet-version: '10.0.x'     # Default: 10.0.x
      configuration: 'Release'      # Default: Release
      runs-on: 'ubuntu-latest'      # Default: ubuntu-latest
      working-directory: '.'        # Default: .
      project-path: '.'             # Default: .
      nuget-source: 'https://api.nuget.org/v3/index.json'
      skip-duplicate: true          # Default: true
    secrets:
      nuget-api-key: ${{ secrets.NUGET_API_KEY }}
```

**Includes:** Build + Test + Code Quality + Pack + Publish

### .NET Application CI Stage
Complete CI pipeline for .NET applications.

**Path:** `.github/workflows/templates/stages/dotnet-app-ci.yml`

```yaml
jobs:
  ci:
    uses: ./.github/workflows/templates/stages/dotnet-app-ci.yml
    with:
      dotnet-version: '10.0.x'     # Default: 10.0.x
      configuration: 'Release'      # Default: Release
      runs-on: 'ubuntu-latest'      # Default: ubuntu-latest
      working-directory: '.'        # Default: .
      enable-code-quality: true     # Default: true
```

**Includes:** Build + Test + Code Quality

## 📖 Examples

See the `examples/` directory for complete workflow examples:

- **pr-validation.yml** - PR validation using stage workflow
- **build-multiplatform.yml** - Multi-platform build matrix using job workflows
- **publish-nuget.yml** - Full NuGet publishing using stage workflow
- **library-ci-stage.yml** - Library CI using stage workflow
- **library-ci-jobs.yml** - Library CI manually composing job workflows
- **simple-ci.yml** - Simple CI using composite actions only
- **custom-workflow.yml** - Custom workflow mixing jobs and actions

## 🎯 Best Practices

### 1. Use Caching
Always enable NuGet caching to speed up builds:

```yaml
- uses: ./.github/actions/nuget/setup-cache
```

### 2. Chain Operations Efficiently
Use `no-restore` and `no-build` flags to avoid redundant work:

```yaml
- uses: ./.github/actions/dotnet/restore
- uses: ./.github/actions/dotnet/build
  with:
    no-restore: 'true'
- uses: ./.github/actions/dotnet/test
  with:
    no-build: 'true'
```

### 3. Run Tests on Multiple Platforms
Use a matrix strategy for cross-platform validation:

```yaml
strategy:
  matrix:
    os: [ubuntu-latest, windows-latest, macos-latest]
runs-on: ${{ matrix.os }}
```

### 4. Collect and Publish Test Results
Always publish test results, even on failure:

```yaml
- uses: ./.github/actions/dotnet/test
- uses: ./.github/actions/diagnostics/publish-test-results
  if: always()
```

### 5. Pin Action Versions
For production workflows, pin to specific versions or tags:

```yaml
uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/actions/dotnet/setup@v1.0.0
```

### 6. Use Secrets for Sensitive Data
Never hardcode API keys or tokens:

```yaml
api-key: ${{ secrets.NUGET_API_KEY }}
```

## 🔶 Azure DevOps Templates

This repository also includes Azure DevOps pipeline templates in the `devops-example/` directory.

### Using Azure DevOps Templates

Reference templates in your pipeline:

```yaml
resources:
  repositories:
  - repository: templates
    type: github
    name: HoneyDrunkStudios/HoneyDrunk.Actions
    endpoint: GitHubConnection

stages:
- template: devops-example/templates/stages/pr-validation.stage.yaml@templates
  parameters:
    dotNetVersion: '10.0.x'
    buildConfiguration: 'Release'
```

### Architecture Philosophy

Both template libraries follow the same hierarchical pattern:

| Level | Azure DevOps | GitHub Actions | Purpose |
|-------|--------------|----------------|---------|
| Steps | Step Templates | Composite Actions | Primitive operations |
| Jobs | Job Templates | Job-Level Workflows | Units of work |
| Stages | Stage Templates | Stage-Level Workflows | Complete pipelines |

This parallel structure makes it easy to understand and maintain both systems.

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
