# Azure AI Speech for the teach bar microphone. The browser streams audio straight to this
# resource with a short-lived Entra ID token the API mints; no key exists (local auth off).
# Entra ID authentication with the Speech SDK needs a custom subdomain, which cannot be changed
# once set. Public network access stays on because the browser connects to it directly.
resource "azurerm_cognitive_account" "speech" {
  name                          = "spch-${local.name_suffix}"
  resource_group_name           = azurerm_resource_group.main.name
  location                      = azurerm_resource_group.main.location
  kind                          = "SpeechServices"
  sku_name                      = "S0"
  custom_subdomain_name         = "spch-${local.name_suffix}-${local.unique}"
  local_auth_enabled            = false
  public_network_access_enabled = true
  tags                          = merge(local.tags, { purpose = "speech-recognition" })
}

# The identity that mints the tokens handed to the browser. A token for cognitiveservices.azure.com
# is valid on every Azure AI services resource where its identity holds a role, so this identity
# holds one role on this one resource and nothing else, and the workload identity never mints
# speech tokens.
resource "azurerm_user_assigned_identity" "speech" {
  name                = "id-${var.project}-speech-${var.environment}-${var.location_short}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = merge(local.tags, { purpose = "speech-recognition" })
}

# The API pod's service account federates to this identity as well as to the workload identity;
# the API names this identity's client id when it mints a speech token.
resource "azurerm_federated_identity_credential" "speech" {
  name                = "aks-${var.workload_namespace}-${var.workload_service_account}"
  resource_group_name = azurerm_resource_group.main.name
  parent_id           = azurerm_user_assigned_identity.speech.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = azurerm_kubernetes_cluster.main.oidc_issuer_url
  subject             = "system:serviceaccount:${var.workload_namespace}:${var.workload_service_account}"
}

resource "azurerm_role_assignment" "speech_identity_speech_user" {
  scope                = azurerm_cognitive_account.speech.id
  role_definition_name = "Cognitive Services Speech User"
  principal_id         = azurerm_user_assigned_identity.speech.principal_id
  principal_type       = "ServicePrincipal"
}

# The owner can try the resource directly (Speech Studio, REST); the API never mints with this grant.
resource "azurerm_role_assignment" "owner_speech_user" {
  scope                = azurerm_cognitive_account.speech.id
  role_definition_name = "Cognitive Services Speech User"
  principal_id         = var.owner_principal_id
  principal_type       = "User"
}
