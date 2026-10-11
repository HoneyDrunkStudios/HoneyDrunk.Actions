# NuGet trusted publishing

NuGet validates the repository that owns the OIDC job. A caller cannot obtain a
valid token inside our cross-repository reusable `release.yml`. Keep build/test,
security checks and packing in that workflow, and run the publishing composite
in a job defined in the package repository itself.

1. Configure a NuGet GitHub trusted-publisher policy for the exact repository,
   caller workflow filename and `nuget` GitHub environment. Limit push permission
   to the repository's actual package IDs; do not grant unlisting.
2. Create that environment with custom deployment branches: `main` and only the
   release tag patterns accepted by that caller. Protect main through review.
3. Call `release.yml` with `enable-nuget-pack: true`,
   `enable-nuget-publish: false`, and `create-github-release: false`. Keep all other
   existing build, scan and container inputs. Remove the NuGet secret binding.
4. In the caller's next job, require successful release and prepare jobs, set
   `environment: nuget`, `contents: write`, `id-token: write`, check out the caller
   with full history, and check out a reviewed immutable Actions revision.
5. Download this run's `nuget-packages` artifact, set up .NET, and call
   `.github/actions/nuget/trusted-publish` with the NuGet username, expected version
   and exact newline-separated package IDs. This validates the complete artifact
   set before login, then uses the short-lived token only for the push.
6. Generate release notes and create the GitHub Release only after push succeeds.
   Preserve the caller's title, tag, prerelease and package metadata.

A separate job in the same caller workflow may use `verify-only: 'true'` for
manual verification from main. It requires the same environment and permissions,
but does not build, push, create tags or create a GitHub Release. A successful
exchange verifies the trust relationship, not a completed package publication.
Verify the first genuine package release separately. Retain the old key until
all callers are migrated and a genuine trusted release has succeeded; never use
automatic fallback to the old key, which would hide a broken trust policy.

The action exposes no credential outputs. The sole API-key reference is the
official NuGet login action's masked, short-lived output, passed to the push via
an environment variable. No stored NuGet secret is needed by migrated callers.
Legacy API-key callers remain compatible during migration.

Use a unique concurrency group for each caller workflow with cancellation off.
Do not rerun a partially published multi-package release blindly: duplicate
versions intentionally fail. Inspect which immutable versions were accepted and
complete recovery through a reviewed release operation.

Sources: [NuGet trusted publishing](https://learn.microsoft.com/en-us/nuget/nuget-org/trusted-publishing),
[official login action](https://github.com/NuGet/login), and
[cross-repository reusable workflow limitation](https://github.com/NuGet/NuGetGallery/issues/11000).
