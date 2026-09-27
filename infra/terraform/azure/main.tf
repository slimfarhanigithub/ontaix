# Ontaix — Azure environment.
# Names follow <type>-<project>-<environment>-<region>. Resources whose names must be
# globally unique also carry a short, stable hash of their fixed inputs.

data "azurerm_client_config" "current" {}

locals {
  name_suffix = "${var.project}-${var.environment}-${var.location_short}"
  compact     = "${var.project}${var.environment}${var.location_short}"
  unique      = substr(sha1("${var.subscription_id}-${local.name_suffix}"), 0, 5)

  tags = {
    project     = var.project
    environment = var.environment
    owner       = var.owner
    purpose     = "demo"
    expires     = var.expires_on
    managed-by  = "terraform"
  }
}

# infra/scripts/bootstrap-azure.sh creates this group so the CI identity can be scoped to it;
# Terraform adopts it into state rather than creating it.
import {
  to = azurerm_resource_group.main
  id = "/subscriptions/${var.subscription_id}/resourceGroups/rg-${local.name_suffix}"
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${local.name_suffix}"
  location = var.location
  tags     = local.tags
}

# One identity for the Ontaix workloads (API, gateway, workers). It reads secrets from
# Key Vault through Kubernetes workload identity; no credential is ever mounted.
resource "azurerm_user_assigned_identity" "workload" {
  name                = "id-${local.name_suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = local.tags
}

resource "azurerm_federated_identity_credential" "workload" {
  name                = "aks-${var.workload_namespace}-${var.workload_service_account}"
  resource_group_name = azurerm_resource_group.main.name
  parent_id           = azurerm_user_assigned_identity.workload.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = azurerm_kubernetes_cluster.main.oidc_issuer_url
  subject             = "system:serviceaccount:${var.workload_namespace}:${var.workload_service_account}"
}
