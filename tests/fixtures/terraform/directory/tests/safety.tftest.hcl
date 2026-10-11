mock_provider "azuread" {}
mock_provider "azapi" {}
mock_provider "msgraph" {}

run "real_directory_schemas" {
  command = plan
  assert {
    condition     = azuread_application.smoke.display_name == "synthetic-directory-smoke"
    error_message = "The real AzureAD schema must plan the synthetic application."
  }
  assert {
    condition     = azapi_resource.smoke.name == "rg-synthetic-smoke"
    error_message = "The real AzAPI schema must plan the synthetic ARM resource."
  }
  assert {
    condition     = msgraph_resource.smoke.url == "applications"
    error_message = "The real Microsoft Graph schema must plan the synthetic resource."
  }
}
