# Fixed public address of the cluster's ingress controller. The deploy workflow binds the
# ingress-nginx LoadBalancer service to this address (annotations azure-pip-name and
# azure-load-balancer-resource-group), so the address and its DNS label outlive the service;
# without it the cloud provider in the cluster creates a dynamic address in the node resource
# group and the label is released whenever that service is deleted. The label is set here only:
# the deploy workflow checks that the label on this address equals its DNS_LABEL and refuses
# to run otherwise, so the cloud provider never rewrites it.
resource "azurerm_public_ip" "ingress" {
  name                = "pip-${local.name_suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Standard"
  sku_tier            = "Regional"
  allocation_method   = "Static"
  ip_version          = "IPv4"
  zones               = ["1", "2", "3"]
  domain_name_label   = var.ingress_dns_label
  tags                = local.tags

  lifecycle {
    # The cloud provider in the cluster records the service that uses the address in these tags.
    ignore_changes = [
      tags["k8s-azure-service"],
      tags["k8s-azure-cluster-name"],
      tags["k8s-azure-dns-label-service"],
    ]
  }
}

# The cluster identity attaches the address to the cluster's load balancer.
resource "azurerm_role_assignment" "aks_ingress_public_ip" {
  scope                = azurerm_public_ip.ingress.id
  role_definition_name = "Network Contributor"
  principal_id         = azurerm_kubernetes_cluster.main.identity[0].principal_id
  principal_type       = "ServicePrincipal"
}
