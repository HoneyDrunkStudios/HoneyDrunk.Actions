# Nightly Security permission rollout validation

Date: 2026-06-22

Scope: PR #212, `nightly-security.yml` caller-owned `actions: read` rollout compatibility.

## Static validation

- Parsed `.github/workflows/nightly-security.yml` with PyYAML.
- Ran `actionlint .github/workflows/nightly-security.yml`.
- Ran `git diff --check`.
- Reviewed the intended diff after each Grid finding.

## Branch behavior covered by implementation

- Caller has `actions: read`: the workflow-run metadata probe writes a positive job-summary entry and CodeQL remains a hard gate.
- Caller lacks `actions: read`: CodeQL may continue only for the known missing workflow-run metadata path.
- Caller lacks `actions: read` and CodeQL exports SARIF: the workflow records degraded finalization and keeps SARIF artifact handling available.
- Caller lacks `actions: read` and CodeQL does not export SARIF: the workflow fails closed in `Verify degraded CodeQL SARIF output`.
- Probe receives a non-authorization API failure: the workflow fails closed instead of treating it as a missing permission.

## Runtime validation still required

After this PR lands on `main`, run one scheduled or manual caller smoke test from:

- a caller with the full documented baseline, such as `HoneyDrunk.NovOutbox` or `HoneyDrunk.Payments`;
- a caller still missing `actions: read`, such as one of the currently failing public repos.

The expected result is full CodeQL finalization for the updated caller and a visible degraded-finalization warning with retained SARIF artifacts for the under-permissioned caller.
