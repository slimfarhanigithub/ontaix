resource "random_password" "postgres" {
  length      = 40
  special     = false
  min_lower   = 4
  min_upper   = 4
  min_numeric = 4
}

resource "azurerm_postgresql_flexible_server" "main" {
  name                          = "psql-${local.name_suffix}-${local.unique}"
  resource_group_name           = azurerm_resource_group.main.name
  location                      = azurerm_resource_group.main.location
  version                       = var.postgres_version
  sku_name                      = var.postgres_sku_name
  storage_mb                    = var.postgres_storage_mb
  administrator_login           = var.postgres_admin_login
  administrator_password        = random_password.postgres.result
  delegated_subnet_id           = azurerm_subnet.postgres.id
  private_dns_zone_id           = azurerm_private_dns_zone.postgres.id
  public_network_access_enabled = false
  backup_retention_days         = 7
  zone                          = "1"
  tags                          = local.tags

  depends_on = [azurerm_private_dns_zone_virtual_network_link.postgres]
}

resource "azurerm_postgresql_flexible_server_database" "ontaix" {
  name      = var.postgres_database
  server_id = azurerm_postgresql_flexible_server.main.id
  collation = "en_US.utf8"
  charset   = "UTF8"
}

# The API's own login. Terraform generates its password and publishes the URL to Key Vault; the
# login itself is created in the server by the API pod's login step (`python -m app.admin
# ensure-api-login`, run with the administrator's URL), which reads the URL from Key Vault,
# creates the login with that password (or sets it after a rotation) and grants it the two
# NOLOGIN roles. No PostgreSQL provider: the administrator password never enters Terraform's
# provider configuration. Rotate with `terraform apply -replace=random_password.postgres_api`,
# then `kubectl -n ontaix rollout restart deploy/ontaix-api`.
resource "random_password" "postgres_api" {
  length      = 40
  special     = false
  min_lower   = 4
  min_upper   = 4
  min_numeric = 4
}

locals {
  database_url     = "postgresql://${var.postgres_admin_login}:${random_password.postgres.result}@${azurerm_postgresql_flexible_server.main.fqdn}:5432/${var.postgres_database}?sslmode=require"
  database_url_api = "postgresql://${var.postgres_api_login}:${random_password.postgres_api.result}@${azurerm_postgresql_flexible_server.main.fqdn}:5432/${var.postgres_database}?sslmode=require"
}
