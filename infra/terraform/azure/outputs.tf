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

output "ingress_public_ip_name" {
  description = "Name of the ingress public IP; the deploy workflow binds the ingress-nginx service to it (INGRESS_PUBLIC_IP)."
  value       = azurerm_public_ip.ingress.name
}

output "ingress_public_ip_address" {
  value = azurerm_public_ip.ingress.ip_address
}

output "ingress_public_fqdn" {
  description = "The public address of Ontaix: the DNS label on the ingress public IP."
  value       = azurerm_public_ip.ingress.fqdn
}

output "foundry_endpoint" {
  description = "Foundry endpoint (custom subdomain); callers authenticate with Entra ID."
  value       = azurerm_cognitive_account.foundry.endpoint
}

output "foundry_deployment_name" {
  value = azurerm_cognitive_deployment.chat.name
}

output "foundry_claude_endpoint" {
  description = "Endpoint of the Claude Foundry resource (ONTAIX_FOUNDRY_ENDPOINT with anthropic_foundry); callers authenticate with Entra ID."
  value       = azurerm_cognitive_account.claude.endpoint
}

output "speech_resource_id" {
  description = "Full resource id of the Azure AI Speech resource (ONTAIX_SPEECH_RESOURCE_ID)."
  value       = azurerm_cognitive_account.speech.id
}

output "speech_region" {
  description = "Region of the Speech resource (ONTAIX_SPEECH_REGION)."
  value       = azurerm_cognitive_account.speech.location
}

output "speech_endpoint" {
  description = "Speech endpoint on its custom subdomain (ONTAIX_SPEECH_ENDPOINT); callers authenticate with Entra ID."
  value       = azurerm_cognitive_account.speech.endpoint
}

output "speech_identity_client_id" {
  description = "Client id of the identity that mints speech tokens (ONTAIX_SPEECH_CLIENT_ID in the cluster)."
  value       = azurerm_user_assigned_identity.speech.client_id
}
