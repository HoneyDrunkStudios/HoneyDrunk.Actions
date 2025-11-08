# GitHub Actions Template Library - Quick Reference

## ?? Structure Overview

### Step-Level: Actions
Composite actions are building blocks that live in `.github/actions/` - these are your reusable steps.

### Job-Level: Reusable Workflows  
Single-job workflows in `.github/workflows/templates/jobs/` - opinionated units of work.

### Stage-Level: Multi-Job Workflows
Complete CI/CD flows in `.github/workflows/templates/stages/` - full pipelines you can drop into any repo.

---

## ?? Action Categories (Steps)

### .NET SDK Actions
| Action | Path | Purpose |
|--------|------|---------|
| Setup | `.github/actions/dotnet/setup` | Install .NET SDK |
| Restore | `.github/actions/dotnet/restore` | Restore NuGet packages |
| Build | `.github/actions/dotnet/build` | Build project/solution |
| Test | `.github/actions/dotnet/test` | Run tests with coverage |
| Pack | `.github/actions/dotnet/pack` | Create NuGet packages |
| Publish | `.github/actions/dotnet/publish` | Publish application |

### NuGet Actions
| Action | Path | Purpose |
|--------|------|---------|
| Setup Cache | `.github/actions/nuget/setup-cache` | Configure NuGet caching |
| Push | `.github/actions/nuget/push` | Push packages to feed |
| Add Source | `.github/actions/nuget/add-source` | Add custom NuGet source |

### Diagnostics Actions
| Action | Path | Purpose |
|--------|------|---------|
| Debug Identity | `.github/actions/diagnostics/debug-build-identity` | Display build info |
| Validate Naming | `.github/actions/diagnostics/validate-test-naming` | Check test naming |
| Publish Results | `.github/actions/diagnostics/publish-test-results` | Upload test results |

### Security Actions
| Action | Path | Purpose |
|--------|------|---------|
| Vulnerability Scan | `.github/actions/security/vulnerability-scan` | Scan for vulnerabilities |

### PR Actions
| Action | Path | Purpose |
|--------|------|---------|
| Generate Summary | `.github/actions/pr/generate-summary` | Create PR summary |
| Post Comment | `.github/actions/pr/post-comment` | Post PR comment |

---

## ?? Job-Level Workflows

Single-job reusable workflows for specific tasks:

| Workflow | Path | Purpose |
|----------|------|---------|
| Build and Test | `.github/workflows/templates/jobs/build-and-test.yml` | Complete build + test |
| Code Quality | `.github/workflows/templates/jobs/code-quality.yml` | Quality checks |
| Publish NuGet | `.github/workflows/templates/jobs/publish-nuget.yml` | Package publishing |

**Usage:**
```yaml
jobs:
  build:
    uses: ./.github/workflows/templates/jobs/build-and-test.yml
    with:
      dotnet-version: '10.0.x'
```

---

## ?? Stage-Level Workflows

Multi-job workflows for complete CI/CD pipelines:

| Workflow | Path | Purpose |
|----------|------|---------|
| PR Validation | `.github/workflows/templates/stages/pr-validation.yml` | Complete PR validation |
| Library CI | `.github/workflows/templates/stages/dotnet-library-ci.yml` | Build + test library |
| Library Release | `.github/workflows/templates/stages/dotnet-library-release.yml` | Build + test + pack + publish |
| App CI | `.github/workflows/templates/stages/dotnet-app-ci.yml` | Build + test application |

**Usage:**
```yaml
jobs:
  ci:
    uses: ./.github/workflows/templates/stages/dotnet-library-ci.yml
    with:
      dotnet-version: '10.0.x'
      enable-code-quality: true
```

---

## ?? Common Patterns

### Pattern 1: Use a Complete Stage (Recommended)
```yaml
jobs:
  ci:
    uses: ./.github/workflows/templates/stages/dotnet-library-ci.yml
    with:
      dotnet-version: '10.0.x'
```

### Pattern 2: Compose Jobs Manually
```yaml
jobs:
  build:
    uses: ./.github/workflows/templates/jobs/build-and-test.yml
  
  quality:
    uses: ./.github/workflows/templates/jobs/code-quality.yml
```

### Pattern 3: Mix Jobs + Actions
```yaml
jobs:
  build:
    uses: ./.github/workflows/templates/jobs/build-and-test.yml
  
  custom:
    runs-on: ubuntu-latest
    steps:
      - uses: ./.github/actions/dotnet/setup
      - run: echo "Custom step"
```

### Pattern 4: Actions Only (Maximum Control)
```yaml
steps:
  - uses: actions/checkout@v4
  - uses: ./.github/actions/dotnet/setup
  - uses: ./.github/actions/nuget/setup-cache
  - uses: ./.github/actions/dotnet/restore
  - uses: ./.github/actions/dotnet/build
    with:
      no-restore: 'true'
  - uses: ./.github/actions/dotnet/test
    with:
      no-build: 'true'
```

---

## ?? Default Values

| Parameter | Default Value |
|-----------|---------------|
| `dotnet-version` | `10.0.x` |
| `configuration` | `Release` |
| `runs-on` | `ubuntu-latest` |
| `working-directory` | `.` |
| `enable-cache` | `true` |
| `collect-coverage` | `true` |
| `fail-on-severity` | `moderate` |

---

## ?? Configuration Examples

### Custom .NET Version
```yaml
with:
  dotnet-version: '8.0.x'
```

### Debug Configuration
```yaml
with:
  configuration: 'Debug'
```

### Windows Runner
```yaml
with:
  runs-on: 'windows-latest'
```

### Custom Working Directory
```yaml
with:
  working-directory: './src'
```

---

## ?? Common Issues

### Issue: Actions not found
**Solution**: Ensure you're using the correct path format:
```yaml
uses: ./.github/actions/dotnet/setup  # Local repo
uses: owner/repo/.github/actions/dotnet/setup@main  # External repo
```

### Issue: Jobs not found
**Solution**: Use correct path with /jobs/ or /stages/:
```yaml
uses: ./.github/workflows/templates/jobs/build-and-test.yml  # Job-level
uses: ./.github/workflows/templates/stages/dotnet-library-ci.yml  # Stage-level
```

### Issue: Workflow not triggering
**Solution**: Check your trigger configuration:
```yaml
on:
  pull_request:
    branches: [ main ]
  push:
    branches: [ main ]
```

### Issue: Cache not working
**Solution**: Ensure setup-cache is called before restore:
```yaml
- uses: ./.github/actions/nuget/setup-cache
- uses: ./.github/actions/dotnet/restore
```

---

## ??? Architecture Decision: When to Use What

### Use **Stages** when:
- ? You want a complete CI/CD pipeline out-of-the-box
- ? Standard library or app workflow fits your needs
- ? You want consistency across multiple repos
- ? Example: PR validation, library releases

### Use **Jobs** when:
- ? You need custom composition of workflows
- ? You want to add custom jobs alongside standard ones
- ? Different projects need different combinations
- ? Example: Custom deployment after build

### Use **Actions** when:
- ? You need maximum control over step order
- ? Building truly custom workflows
- ? Existing jobs don't fit your needs
- ? Example: Complex multi-stage builds

---

## ?? Performance Tips

1. **Enable caching** - Saves 30-60 seconds on builds
2. **Use `no-restore` flag** - Avoid duplicate restore operations
3. **Use `no-build` flag** - Skip redundant builds during test/pack
4. **Matrix builds** - Run parallel builds for different platforms
5. **Artifact retention** - Set appropriate retention days (default: 30-90)
6. **Use stages for standard workflows** - Pre-optimized job ordering

---

## ?? Quick Links

- [Full Documentation](../README.md)
- [Examples Directory](../examples/)
- [GitHub Actions Docs](https://docs.github.com/en/actions)
- [.NET CLI Reference](https://docs.microsoft.com/en-us/dotnet/core/tools/)
