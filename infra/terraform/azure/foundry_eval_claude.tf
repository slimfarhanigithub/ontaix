# Eval-only Foundry resource for the teach extraction bake-off's Claude candidates. Claude is not
# offered in France Central; in Sweden Central it is GlobalStandard only, so prompts may be
# processed outside the EU data zone and the bake-off never sends the owner's private documents
# to it. Keyless like the main resource. Created only while the deployment map is not empty.
# Claude on Foundry is billed through Azure Marketplace: the subscription must accept Anthropic's
# Marketplace terms, and sponsorship subscriptions may be ineligible.
locals {
  claude_eval_enabled = length(var.foundry_claude_deployments) > 0
  claude_name_suffix  = "${var.project}-${var.environment}-${var.foundry_claude_location_short}-eval"
}

resource "azurerm_cognitive_account" "claude_eval" {
  count                         = local.claude_eval_enabled ? 1 : 0
  name                          = "ais-${local.claude_name_suffix}-${local.unique}"
  resource_group_name           = azurerm_resource_group.main.name
  location                      = var.foundry_claude_location
  kind                          = "AIServices"
  sku_name                      = "S0"
  custom_subdomain_name         = "ais-${local.claude_name_suffix}-${local.unique}"
  local_auth_enabled            = false
  public_network_access_enabled = true
  tags                          = merge(local.tags, { purpose = "eval" })

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_cognitive_deployment" "claude_eval" {
  for_each = var.foundry_claude_deployments

  name                   = each.key
  cognitive_account_id   = azurerm_cognitive_account.claude_eval[0].id
  version_upgrade_option = "NoAutoUpgrade"

  model {
    format  = "Anthropic"
    name    = each.value.model_name
    version = each.value.model_version
  }

  sku {
    name     = "GlobalStandard"
    capacity = each.value.capacity
  }
}

# Inference only, for the owner who runs the bake-off; no workload calls this resource.
resource "azurerm_role_assignment" "owner_claude_eval_user" {
  count                = local.claude_eval_enabled ? 1 : 0
  scope                = azurerm_cognitive_account.claude_eval[0].id
  role_definition_name = "Cognitive Services User"
  principal_id         = var.owner_principal_id
  principal_type       = "User"
}
