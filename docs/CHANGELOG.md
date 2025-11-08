# Changelog

All notable changes to the GitHub Actions template library will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

### Planned
- Docker container support
- Azure deployment actions
- Code coverage reporting with trending
- Integration with SonarQube
- Database deployment actions
- Terraform deployment actions
- Multi-repository support
- Custom labeling and tagging
- Slack/Teams notifications
- Release notes generation

---

For migration guides and breaking changes, see [MIGRATION.md](MIGRATION.md) (when applicable).
