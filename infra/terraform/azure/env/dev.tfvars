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
