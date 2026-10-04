# Ontaix development / demo environment, France Central.
# subscription_id is supplied by CI (TF_VAR_subscription_id) or the owner locally; it is not committed.
location       = "francecentral"
location_short = "frc"
environment    = "dev"
owner          = "slim.farhani"
owner_email    = "slim.farhani@insight.com"
expires_on     = "2026-12-31"

ci_principal_id    = "71d90769-0f46-4a8c-8dfb-34eb38340491"
owner_principal_id = "f96c0bc9-02ac-48da-999d-ca0092c3c362"

monthly_budget_eur = 400

aks_node_vm_size   = "Standard_D4s_v5"
aks_node_count_min = 1
aks_node_count_max = 3

postgres_sku_name   = "B_Standard_B2s"
postgres_storage_mb = 32768

foundry_public_network_access_enabled = true
foundry_deployment_name               = "gpt-6-sol"
foundry_model_version                 = "2026-09-22"
foundry_deployment_sku                = "DataZoneStandard"
# 3,000,000 tokens and 3,000 requests per minute. The subscription's quota for
# OpenAI.DataZoneStandard.gpt-6-sol in France Central is 3,333 units and this is its only
# deployment, so 333 units stay free for a second deployment (an evaluation or a newer model
# version beside this one) without a quota request. Capacity on this SKU is not billed; usage is.
foundry_deployment_capacity = 3000

# The public address of Ontaix: ontaix-dev.francecentral.cloudapp.azure.com.
ingress_dns_label = "ontaix-dev"

# Teach extraction models: Claude, GlobalStandard in Sweden Central (not EU data zone).
# Versions as listed by `az cognitiveservices model list --location swedencentral` on 2026-09-29.
foundry_claude_location = "swedencentral"
foundry_claude_organization = {
  name         = "Insight"
  country_code = "FR"
  industry     = "technology"
}
foundry_claude_deployments = {
  "claude-fable-5-1"  = { model_version = "1", capacity = 50 }
  "claude-sonnet-5-5" = { model_version = "2", capacity = 50 }
  "claude-sonnet-5"   = { model_version = "2", capacity = 50 }
}
