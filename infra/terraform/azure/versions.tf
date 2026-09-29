terraform {
  required_version = ">= 1.9.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    azapi = {
      source  = "azure/azapi"
      version = "~> 2.0"
    }
  }

  # State lives in the storage account created by infra/scripts/bootstrap-azure.sh.
  # The account, container and key are passed with -backend-config so this file holds
  # no environment-specific value. Access is Entra ID only; shared keys are disabled.
  backend "azurerm" {
    use_azuread_auth = true
  }
}

# Claude deployments need `modelProviderData`, which azurerm_cognitive_deployment does not expose.
provider "azapi" {
  subscription_id = var.subscription_id
}

provider "azurerm" {
  subscription_id = var.subscription_id
  # OIDC federation in CI (ARM_USE_OIDC=true); the signed-in Azure CLI locally.
  features {
    key_vault {
      purge_soft_delete_on_destroy = false
    }
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }
}
