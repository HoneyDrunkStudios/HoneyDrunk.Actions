# Real Terraform fixture

The reusable workflow exercises two Terraform assertions in `plan/tests` using
the real pinned CLI/provider, disabled backend, shared lock and mocked plans.
The Python ownership check ensures this fixture stays limited to one synthetic
plan with an unconfigured backend and no data sources or provider configuration.
Infrastructure supplies a broader ownership suite as the production consumer.
