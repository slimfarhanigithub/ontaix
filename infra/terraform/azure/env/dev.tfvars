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
foundry_deployment_capacity           = 100

# Teach extraction bake-off candidates (GPT) and the OCR model for scanned PDFs, which is not a
# candidate. All DataZoneStandard in France Central.
# Names, versions and SKUs as listed by `az cognitiveservices model list --location francecentral`
# on 2026-09-29. Empty the map once the bake-off is decided.
foundry_eval_deployments = {
  "gpt-6-luna"      = { model_name = "gpt-6-luna", model_version = "2026-09-22" }
  "gpt-5.6-sol"     = { model_name = "gpt-5.6-sol", model_version = "2026-07-09" }
  "gpt-5.6-terra"   = { model_name = "gpt-5.6-terra", model_version = "2026-07-09" }
  "gpt-5.6-luna"    = { model_name = "gpt-5.6-luna", model_version = "2026-07-09" }
  "gpt-5.5"         = { model_name = "gpt-5.5", model_version = "2026-04-24" }
  "gpt-5.4"         = { model_name = "gpt-5.4", model_version = "2026-03-05" }
  "o3"              = { model_name = "o3", model_version = "2025-04-16" }
  "mistral-ocr-4-0" = { model_name = "mistral-ocr-4-0", model_version = "1", model_format = "Mistral AI", capacity = 10 }
}

# Claude candidates on the eval-only Sweden Central resource (GlobalStandard: not EU data zone).
# Versions as listed by `az cognitiveservices model list --location swedencentral` on 2026-09-29.
foundry_claude_deployments = {
  "claude-fable-5-1"  = { model_name = "claude-fable-5-1", model_version = "1" }
  "claude-opus-5-5"   = { model_name = "claude-opus-5-5", model_version = "2" }
  "claude-sonnet-5-5" = { model_name = "claude-sonnet-5-5", model_version = "2" }
  "claude-haiku-4-5"  = { model_name = "claude-haiku-4-5", model_version = "20251001" }
}
