# Development App Service container release

`job-deploy-app-service.yml` is a development-only reusable workflow for direct
single-container image updates. It has no slots, production dispatch, SQL,
network/configuration provisioning or automatic rollback. Other deploy workflows
and the older slot-oriented composite remain unchanged.

The caller supplies `operation` (`deploy`/`rollback`), ACR `registry-name`,
`image-name`, and the retained `rollback-image`/`rollback-release-id` only for
rollback. It must provide a reviewed `scripts/deploy_app_service.py` accepting
`--app-name`, `--image`, `--release-id` and writing `deployment-evidence/`.
That product-owned verifier enforces its resource/image scope and validates
actual release identity plus readiness. The caller Dockerfile must consume
`RELEASE_ID` so the running image can prove its build identity.

The caller's protected `dev` environment supplies `APP_SERVICE_NAME`,
`APP_SERVICE_DEPLOYMENT_APPROVED=true`, `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`
and `AZURE_SUBSCRIPTION_ID`. At least one required environment reviewer must exist;
all gates are checked before OIDC login. Callers grant only contents:read and
id-token:write and serialize deployments with a product/environment concurrency
group. The workflow runs only for refs/heads/main. Variables/permissions are
configured only after separate approval; a merged workflow creates none of them.

A deploy builds a unique image, scans the local image archive with the existing
release tool pin `aquasec/trivy:0.69.3` (no Docker socket or cloud credentials
mounted), rejects HIGH/CRITICAL vulnerabilities or scanner failures, then pushes
to ACR. Rollback rescans the exact retained digest. No ignore-unfixed or failure
suppression is configured. The application verifier must fail closed, preserve
pre-write rollback evidence and distinguish old healthy images from the selected
release. Artifacts are retained even on failure; a failed update is not a rollback.

Current consumer: HoneyDrunk.Identity PR #3. Its tested verifier owns the exact
Identity development resource names, digest policy, three consecutive health
observations and unchanged-image configuration readback. Shared shell regressions
run without Azure access; live deployment/rollback acceptance is a separate gate.
