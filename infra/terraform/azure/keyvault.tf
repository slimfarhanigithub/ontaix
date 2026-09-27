resource "azurerm_key_vault" "main" {
  name                       = "kv-${local.name_suffix}-${local.unique}"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  purge_protection_enabled   = false
  soft_delete_retention_days = 7
  tags                       = local.tags
}

# Both deployers write secrets: the CI identity and the owner running Terraform locally. The
# grants name fixed principals so the plan is the same whoever runs it; the workload reads.
resource "azurerm_role_assignment" "ci_secrets_officer" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = var.ci_principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "owner_secrets_officer" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = var.owner_principal_id
  principal_type       = "User"
}

resource "azurerm_role_assignment" "workload_secrets_user" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.workload.principal_id
}

resource "azurerm_key_vault_secret" "postgres_admin_password" {
  name         = "postgres-admin-password"
  value        = random_password.postgres.result
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.ci_secrets_officer, azurerm_role_assignment.owner_secrets_officer]
}

resource "azurerm_key_vault_secret" "database_url" {
  name         = "database-url"
  value        = local.database_url
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.ci_secrets_officer, azurerm_role_assignment.owner_secrets_officer]
}
