mock_provider "azurerm" {}

run "bounded_plan" {
  command = plan
  assert {
    condition     = azurerm_service_plan.smoke.os_type == "Linux" && azurerm_service_plan.smoke.sku_name == "B1"
    error_message = "Real CLI must evaluate the plan against the mocked AzureRM schema."
  }
}

run "reject_unapproved_tier" {
  command = plan
  variables { sku = "P1v3" }
  expect_failures = [var.sku]
}
