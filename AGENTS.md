# HoneyDrunk.Actions agent instructions

Own reusable GitHub Actions workflows and composite actions, not application rules or resource templates. Read [the workflow guide](docs/engineering-guide.md), [consumer usage](docs/consumer-usage.md) and the actual callers before changing workflow contracts. Keep permissions minimal, input/secret names and defaults compatible, and verify reusable-workflow behavior at the consumer boundary. Do not introduce packet/ticket generation or retired PR review infrastructure.

Read the [shared engineering conventions](https://github.com/HoneyDrunkStudios/HoneyDrunk.Standards/blob/main/HoneyDrunk.Standards/docs/CONVENTIONS.md) and this repository's owning documentation before editing. Apply the parts relevant to this stack; preserve existing public contracts, dependency direction and repository-specific behavior. Verify shared capabilities in current code before reusing them; a catalog entry or scaffold is not an implemented integration.

Work within the selected request. Preserve unrelated changes and use a separate worktree when needed. Review the final diff, use Conventional Commits and ready-for-review PRs with exactly one accurate `Authorship:` line and a `Request:` line; include the authorship in commit trailers. Run meaningful checks for the affected behavior and report the reviewed/tested revision, failures and unrun checks. For documentation-only changes, check links, paths and instruction consistency. Preserve required checks and inspect actual latest-head Sonar new-code findings where analysis applies; do not suppress findings or weaken gates to obtain a pass. Legacy Grid Review is retired; do not restore its workers, queues or bypass labels. A configured replacement reviewer is not evidence of a completed review or enforcing merge check.

## Verification

Use [.github/workflows/actions-ci.yml](.github/workflows/actions-ci.yml) for the current pinned actionlint setup, Python dependencies and contract-test commands. Run the tests matching changed behavior, for example `python -m unittest discover -s tests -p test_pr_metadata.py -v` for PR metadata and `python -m unittest discover -s tests -p test_review_retirement.py -v` for retirement guards. For YAML changes, run actionlint as CI does. Never dispatch a deployment, rotation or paid review merely to verify documentation.

## Code Review Rules

Apply the [shared review criteria](https://github.com/HoneyDrunkStudios/HoneyDrunk.Standards/blob/main/HoneyDrunk.Standards/docs/CONVENTIONS.md#code-review) to changed behavior, using the repository boundaries above. Report actionable findings with the failing path, concrete impact and a small corrective action; disclose unavailable evidence. These rules grant no cross-repository access or merge authority.

- Trace reusable workflow changes through real callers: preserve inputs, outputs, secret names, defaults and caller/job permissions. Keep application decisions in consumers and resource definitions in Infrastructure; reuse existing workflow helpers only when their behavior fits.
- Flag untrusted-input interpolation, secret-bearing logs/artifacts, privilege escalation, unsafe event/ref conditions, mutable deployment artifacts, or release/rollback paths that can affect the wrong target. Check timeouts, concurrency, cancellation and aggregate gates for failed or skipped prerequisites.
- Require focused caller/contract and failure-path evidence for changed orchestration, including rejected targets and rollback failures where relevant. A YAML lint pass cannot establish safe execution; leave formatting and deterministic inventory checks to CI.
