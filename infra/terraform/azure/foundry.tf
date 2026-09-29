# Azure AI Foundry resource hosting the model the Ontaix workloads call.
# Keyless only: callers authenticate with Entra ID tokens (workload identity in the cluster,
# `az login` locally). Public network access follows the rest of the dev environment;
# a private endpoint in the VNet is a follow-up.
resource "azurerm_cognitive_account" "foundry" {
  name                          = "ais-${local.name_suffix}-${local.unique}"
  resource_group_name           = azurerm_resource_group.main.name
  location                      = azurerm_resource_group.main.location
  kind                          = "AIServices"
  sku_name                      = "S0"
  custom_subdomain_name         = "ais-${local.name_suffix}-${local.unique}"
  local_auth_enabled            = false
  public_network_access_enabled = var.foundry_public_network_access_enabled
  tags                          = local.tags

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_cognitive_deployment" "chat" {
  name                 = var.foundry_deployment_name
  cognitive_account_id = azurerm_cognitive_account.foundry.id

  model {
    format  = "OpenAI"
    name    = var.foundry_model_name
    version = var.foundry_model_version
  }

  sku {
    name     = var.foundry_deployment_sku
    capacity = var.foundry_deployment_capacity
  }
}

# Candidate models for the teach extraction bake-off, beside the default deployment, and the OCR
# model that reads scanned documents. The version is pinned so every run of the bake-off
# compares the same model builds.
resource "azurerm_cognitive_deployment" "eval" {
  for_each = var.foundry_eval_deployments

  name                   = each.key
  cognitive_account_id   = azurerm_cognitive_account.foundry.id
  version_upgrade_option = "NoAutoUpgrade"

  model {
    format  = each.value.model_format
    name    = each.value.model_name
    version = each.value.model_version
  }

  sku {
    name     = "DataZoneStandard"
    capacity = each.value.capacity
  }

  # Azure refuses concurrent deployment changes on one account: waiting for the default
  # deployment avoids a conflict with it; `-parallelism=1` serialises the eval deployments.
  depends_on = [azurerm_cognitive_deployment.chat]
}

# Inference only: the workload and the owner call the deployment; neither manages the account.
resource "azurerm_role_assignment" "workload_foundry_user" {
  scope                = azurerm_cognitive_account.foundry.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_user_assigned_identity.workload.principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "owner_foundry_user" {
  scope                = azurerm_cognitive_account.foundry.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = var.owner_principal_id
  principal_type       = "User"
}
