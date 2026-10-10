terraform {
  required_version = "~> 1.16.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "= 5.9.0"
    }
  }
  # Even an empty remote backend must remain disabled in the real smoke run.
  backend "azurerm" {}
}

variable "sku" {
  type    = string
  default = "B1"
  validation {
    condition     = var.sku == "B1"
    error_message = "Fixture models a bounded development plan."
  }
}

resource "azurerm_service_plan" "smoke" {
  name                = "asp-hd-smoke-dev"
  resource_group_name = "rg-hd-smoke-dev"
  location            = "eastus2"
  os_type             = "Linux"
  sku_name            = var.sku
  worker_count        = 1
}
