# Foundry resource for the Claude teach extraction models. Claude is not offered in
# France Central; in Sweden Central it is GlobalStandard only, so prompts may be processed
# outside the EU data zone. Keyless like the main resource: callers authenticate with Entra ID
# tokens. Claude on Foundry is billed through Azure Marketplace: the subscription must accept
# Anthropic's Marketplace terms, and sponsorship subscriptions may be ineligible.
locals {
  claude_name_suffix = "${var.project}-${var.environment}-${var.foundry_claude_location_short}"
}

resource "azurerm_cognitive_account" "claude" {
  name                          = "ais-${local.claude_name_suffix}-${local.unique}"
  resource_group_name           = azurerm_resource_group.main.name
  location                      = var.foundry_claude_location
  kind                          = "AIServices"
  sku_name                      = "S0"
  custom_subdomain_name         = "ais-${local.claude_name_suffix}-${local.unique}"
  local_auth_enabled            = false
  public_network_access_enabled = var.foundry_public_network_access_enabled
  tags                          = merge(local.tags, { purpose = "teach-extraction" })

  identity {
    type = "SystemAssigned"
  }
}

# Each deployment carries the organisation attestation Anthropic's Marketplace offer requires;
# Azure accepts the offer with it on the subscription's behalf. Deployments on one account are
# created one at a time (apply with -parallelism=1) because the account refuses concurrent writes.
resource "azapi_resource" "claude_deployment" {
  for_each = var.foundry_claude_deployments

  type                      = "Microsoft.CognitiveServices/accounts/deployments@2025-10-01-preview"
  name                      = each.key
  parent_id                 = azurerm_cognitive_account.claude.id
  schema_validation_enabled = false

  body = {
    sku = {
      name     = "GlobalStandard"
      capacity = each.value.capacity
    }
    properties = {
      model = {
        format  = "Anthropic"
        name    = each.key
        version = each.value.model_version
      }
      modelProviderData = {
        organizationName = var.foundry_claude_organization.name
        countryCode      = var.foundry_claude_organization.country_code
        industry         = var.foundry_claude_organization.industry
      }
      versionUpgradeOption = "NoAutoUpgrade"
    }
  }

  depends_on = [
    azurerm_role_assignment.workload_claude_user,
    azurerm_role_assignment.owner_claude_user,
  ]
}

# Inference only: the workload and the owner call the deployment; neither manages the account.
resource "azurerm_role_assignment" "workload_claude_user" {
  scope                = azurerm_cognitive_account.claude.id
  role_definition_name = "Cognitive Services User"
  principal_id         = azurerm_user_assigned_identity.workload.principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "owner_claude_user" {
  scope                = azurerm_cognitive_account.claude.id
  role_definition_name = "Cognitive Services User"
  principal_id         = var.owner_principal_id
  principal_type       = "User"
}
