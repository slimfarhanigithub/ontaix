resource "azurerm_kubernetes_cluster" "main" {
  name                = "aks-${local.name_suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  dns_prefix          = local.name_suffix
  kubernetes_version  = var.aks_kubernetes_version
  sku_tier            = "Free"
  tags                = local.tags

  # Workload identity: pods authenticate to Azure with a projected token, never a secret.
  oidc_issuer_enabled       = true
  workload_identity_enabled = true

  # Entra ID authenticates every caller of the Kubernetes API and Azure RBAC authorizes it: a
  # kubeconfig holds no credential, only the kubelogin exec plugin, and access is an Azure role
  # assignment (below) that expires with its token and is revoked by removing the assignment.
  # No admin group: the owner and the CI identity hold Azure Kubernetes Service RBAC Cluster
  # Admin as assignments, which Azure audits.
  azure_active_directory_role_based_access_control {
    azure_rbac_enabled = true
    tenant_id          = data.azurerm_client_config.current.tenant_id
  }

  # Off until the Entra path is verified (docs/provisioning.md, Cluster Access): with local
  # accounts on, `az aks get-credentials --admin` still hands out a long-lived cluster-admin
  # certificate to any Contributor; with them off it is refused and only Entra identities enter.
  local_account_disabled = var.aks_local_accounts_disabled

  default_node_pool {
    name                        = "system"
    vm_size                     = var.aks_node_vm_size
    vnet_subnet_id              = azurerm_subnet.aks.id
    auto_scaling_enabled        = true
    min_count                   = var.aks_node_count_min
    max_count                   = var.aks_node_count_max
    os_disk_size_gb             = 64
    temporary_name_for_rotation = "systemtmp"
    upgrade_settings {
      max_surge = "33%"
    }
  }

  identity {
    type = "SystemAssigned"
  }

  network_profile {
    network_plugin      = "azure"
    network_plugin_mode = "overlay"
    network_policy      = "cilium"
    network_data_plane  = "cilium"
    load_balancer_sku   = "standard"
    outbound_type       = "loadBalancer"
  }

  oms_agent {
    log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  }

  lifecycle {
    ignore_changes = [default_node_pool[0].node_count]
  }
}

# The cluster identity must manage the subnet it deploys into.
resource "azurerm_role_assignment" "aks_subnet" {
  scope                = azurerm_subnet.aks.id
  role_definition_name = "Network Contributor"
  principal_id         = azurerm_kubernetes_cluster.main.identity[0].principal_id
}

# Kubernetes access through Azure RBAC. Both assignments are made by the owner's local apply:
# the CI identity holds no Role Based Access Control Administrator assignment (the subscription's
# conditioned Owner cannot delegate it), so a CI apply of a new role assignment is refused.
#
# The owner: full control, the account that recovers the cluster.
resource "azurerm_role_assignment" "owner_aks_cluster_admin" {
  scope                = azurerm_kubernetes_cluster.main.id
  role_definition_name = "Azure Kubernetes Service RBAC Cluster Admin"
  principal_id         = var.owner_principal_id
  principal_type       = "User"
}

# The CI identity: the deploy workflow installs ingress-nginx, cert-manager and the Let's Encrypt
# issuers, which create namespaces, custom resource definitions, cluster roles and cluster role
# bindings, webhook configurations, an ingress class and cluster issuers. Azure Kubernetes
# Service RBAC Writer is namespaced and covers none of these, and an identity that writes
# cluster role bindings can bind itself to cluster-admin anyway, so a narrower role would only
# hide the same power. Cluster Admin at the cluster scope is the honest minimum while the
# platform charts are installed by the workflow; it becomes Writer on the three namespaces the
# day the owner installs those charts himself.
resource "azurerm_role_assignment" "ci_aks_cluster_admin" {
  scope                = azurerm_kubernetes_cluster.main.id
  role_definition_name = "Azure Kubernetes Service RBAC Cluster Admin"
  principal_id         = var.ci_principal_id
  principal_type       = "ServicePrincipal"
}
