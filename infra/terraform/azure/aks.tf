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
