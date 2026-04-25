# Changelog

All notable changes to the GitHub Actions template library will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] - 2026-04-18

### Added
- `job-dependency-scan.yml`: PR-time vulnerable-package scan (`dotnet list package --vulnerable --include-transitive`). Emits severity counts, uploads JSON report artifact, fails on configurable severity threshold.
- `pr-core.yml`: wired in the dependency-scan job as optional (default on), with `enable-dependency-scan` and `dependency-fail-on-severity` inputs. Results appear in the PR summary comment alongside existing jobs.
- `pr-sdk.yml`: same dependency-scan wiring for SDK/library repos; findings + severity breakdown show up in the SDK PR comment.
- `job-codeql.yml`: PR-time CodeQL SAST + code-quality scan using the `security-and-quality` query pack (same suite nightly runs). Uploads SARIF to Code Scanning under a `pr-sast` category, emits severity counts, and fails the PR at or above a configurable SARIF level (default: any finding).
- `pr-core.yml` and `pr-sdk.yml`: wired in the CodeQL job as optional (default on) with `enable-codeql`, `codeql-queries`, and `codeql-fail-on-severity` inputs. Findings + severity breakdown appear in the PR summary comment.

### Changed
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

### Added
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
