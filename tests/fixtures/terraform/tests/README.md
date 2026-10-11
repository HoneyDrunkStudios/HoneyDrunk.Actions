# Real Terraform fixture

The reusable workflow exercises two AzureRM runs in `plan/tests` and one combined
AzureAD/AzAPI/Microsoft Graph run in `directory/tests`, using the real pinned CLI
and provider schemas, disabled backends, shared lock subsets and mocked plans.
The Python ownership checks keep the resource targets synthetic with unconfigured
backends and no data sources or provider credentials.
Infrastructure supplies a broader ownership suite as the production consumer.
