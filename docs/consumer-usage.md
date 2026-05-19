# Consumer Usage Guide

This document provides sample workflows for consuming repos to adopt the HoneyDrunk.Actions workflow families.

## Table of Contents

- [PR Core Workflow](#pr-core-workflow)
- [PR SDK Workflow](#pr-sdk-workflow)
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

### Minimal Example

```yaml
name: PR Validation

on:
  pull_request:
    branches: [main, develop]
  push:
    branches: [main, develop]

jobs:
  pr-validation:
    uses: HoneyDrunkStudios/HoneyDrunk.Actions/.github/workflows/pr-core.yml@main
```

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

To let the baseline ratchet seed/update after merges, call `pr-core.yml` on `push` to the default branch as well as `pull_request`, and grant the reusable job `contents: write` so it can commit the bot-maintained baseline. A pull-request-only caller still enforces no-regress when `.github/coverage-baseline.json` already exists, but the baseline will not auto-ratchet after merges; if the file does not exist yet, PRs remain in bootstrap mode until it is seeded.

Optional inputs:

```yaml
with:
  patch-coverage-threshold: 75
  absolute-coverage-floor: 70
```

### Full Example with Options

```yaml
name: PR Validation

on:
  pull_request:
    branches: [main, develop]

permissions:
  contents: read  # broader writes are granted per-job (least privilege)

jobs:
  pr-validation:
    # security-events: write is scoped here because pr-core's CodeQL step
    # uploads SARIF to GitHub Code Scanning. checks: write and
    # pull-requests: write are scoped here too so additional jobs don't
    # inherit them implicitly. contents: write is needed only for the
    # default-branch coverage baseline ratchet.
    permissions:
      contents: write
      checks: write
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
      enable-accessibility-check: false
      patch-coverage-threshold: 75
      absolute-coverage-floor: 70
      post-pr-summary: true
      actions-ref: 'main'
    secrets:
      github-token: ${{ secrets.GITHUB_TOKEN }}
```

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

### Worker / Deployable App Release

**When to Use:** Worker services, background processors, or web APIs that need `dotnet publish` artifacts (not NuGet packages, not containers).

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
      project-path: './MyProject.slnx'
      enable-app-publish: true
      publish-projects: 'MyWorker/MyWorker.csproj;MyApi/MyApi.csproj'
      publish-runtime: 'linux-x64'
      publish-self-contained: false

permissions:
  contents: read
  packages: write
  id-token: write
```

### Container with Custom Build Context

**When to Use:** Repos where the Dockerfile is not at the repo root, or the build context differs from the working directory (e.g., solution root is a subdirectory).

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

permissions:
  contents: read
  packages: write
  id-token: write
```

---

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

- Container App name must match `ca-hd-{service}-{env}`.
- Container App `activeRevisionsMode` must be `Multiple`.
- Container App must have system-assigned Managed Identity enabled.
- For Key Vault references, that managed identity must have access to the referenced Key Vault secrets.
- For OIDC deploys, the federated credential needs `AcrPush` on the shared ACR and `Container Apps Contributor` on the target Container App.

---

## Deploy Azure Function App

**Purpose:** Deploy a .NET Azure Function App after building with `release.yml` or a custom build job.

**When to Use:** Repos with Azure Function Apps (queue-triggered, HTTP-triggered, timer-triggered, etc.). Chains after a build job that publishes the function app as an artifact.

### Minimal Example

```yaml
name: Release and Deploy Function

on:
  push:
    tags:
      - 'v*'

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-dotnet@v4
        with:
          dotnet-version: '10.0.x'
      - run: dotnet publish MyProject.Functions/MyProject.Functions.csproj -c Release -o ./publish
      - uses: actions/upload-artifact@v4
        with:
          name: function-app
          path: ./publish

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
