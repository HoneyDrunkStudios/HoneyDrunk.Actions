# Real Terraform fixture

The reusable workflow exercises two Terraform assertions in `plan/tests` using
the real pinned CLI/provider, disabled backend, shared lock and mocked plans.
No Python ownership suite is needed for this synthetic single-resource fixture;
Infrastructure supplies its own ownership suite as the production consumer.
