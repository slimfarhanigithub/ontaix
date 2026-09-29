output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

output "aks_cluster_name" {
  value = azurerm_kubernetes_cluster.main.name
}

output "aks_oidc_issuer_url" {
  value = azurerm_kubernetes_cluster.main.oidc_issuer_url
}

output "acr_login_server" {
  value = azurerm_container_registry.main.login_server
}

output "key_vault_name" {
  value = azurerm_key_vault.main.name
}

output "postgres_fqdn" {
  value = azurerm_postgresql_flexible_server.main.fqdn
}

output "workload_identity_client_id" {
  description = "Set as azure.workload.identity/client-id on the ontaix-api service account."
  value       = azurerm_user_assigned_identity.workload.client_id
}

output "log_analytics_workspace_id" {
  value = azurerm_log_analytics_workspace.main.id
}

output "foundry_endpoint" {
  description = "Foundry endpoint (custom subdomain); callers authenticate with Entra ID."
  value       = azurerm_cognitive_account.foundry.endpoint
}

output "foundry_deployment_name" {
  value = azurerm_cognitive_deployment.chat.name
}
