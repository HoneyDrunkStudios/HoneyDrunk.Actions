# Terraform source validation

`job-terraform-validate.yml` replaces the Infrastructure repository's Bicep PR
gate. Consumers pin both the reusable workflow and `actions-ref` to the same
reviewed 40-character commit. The workflow checks out that commit's helper;
it never executes a mutable `main` helper behind a pinned workflow.

The caller supplies `.terraform-version` (currently `1.16.5`), one reviewed root
`.terraform.lock.hcl`, a `terraform-roots.json` array, and `tests/safety.tftest.hcl`
in every root and two-level concern module. The helper checks all declared roots
and `modules/*/*`, copies the shared lock, and runs format, backend-disabled
initialization with a read-only lock, schema validation and mocked plan tests.

`working-directory` defaults to the caller repository root. A nested caller may
select a relative directory inside that checkout; absolute paths, traversal and
symlink escapes are rejected. Actions CI calls this same workflow at its own
revision against `tests/fixtures/terraform`, exercising the real CLI, AzureRM
schema, backend-disabled initialization, shared-lock copies and JSON test results
on every PR. The fixture includes both a successful plan and a rejected tier.
Every test must explicitly use the mocked AzureRM provider and `command = plan`.
Root duplication/path traversal, real test providers, alternate test modules,
and test applies fail before invoking Terraform. New provider kinds require a
reviewed contract change. Initialization still downloads checksummed providers;
"credential-free" does not mean network-free.

The runner requires exactly one `tests/safety.tftest.hcl` per target and checks
Terraform's JSON summary against the number of declared tests: missing, zero,
failed, skipped or warning-bearing test results fail. Additional unmocked provider
types are rejected. The caller's Python ownership tests also run via unittest.

Permissions are `contents: read`. There is no Azure login, OIDC permission,
backend initialization, live plan, import, apply, state upload or plan artifact.
No third-party Terraform marketplace wrapper is used (Grid invariant 38).
The CLI archive is verified against HashiCorp's published SHA-256 manifest.

The ordinary secret scan, Sonar/security policy and branch protections remain
separate required controls. This job does not claim live Azure validation.
Deployment/state operations need a separately approved protected-environment
workflow; do not add a mode switch to this PR-safe validation job.

The existing Bicep reusable workflows remain for compatibility with other
consumers; they are not current Infrastructure callers.
[App Service runtime delivery](app-service-development.md) is a separate
capability from the merged Terraform source-validation workflow. Neither
workflow documentation nor a source merge configures access or authorizes deployment.
