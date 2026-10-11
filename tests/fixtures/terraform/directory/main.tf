terraform {
  required_version = "~> 1.16.0"
  backend "azurerm" {}
  required_providers {
    azuread = {
      source  = "hashicorp/azuread"
      version = "= 3.10.0"
    }
    azapi = {
      source  = "Azure/azapi"
      version = "= 2.13.0"
    }
    msgraph = {
      source  = "Microsoft/msgraph"
      version = "= 0.6.0"
    }
  }
}

resource "azuread_application" "smoke" {
  display_name = "synthetic-directory-smoke"
}

resource "azapi_resource" "smoke" {
  type      = "Microsoft.Resources/resourceGroups@2021-04-01"
  name      = "rg-synthetic-smoke"
  parent_id = "/subscriptions/00000000-0000-4000-8000-000000000001"
  location  = "eastus2"
  body      = { properties = {} }
}

resource "msgraph_resource" "smoke" {
  url         = "applications"
  api_version = "v1.0"
  body        = { displayName = "synthetic-graph-smoke" }
}
