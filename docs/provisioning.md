# Provisioning

Azure, France Central, one environment (`dev`) used for development and demos. Infrastructure is
Terraform (`infra/terraform/azure`), applied by GitHub Actions through OIDC federation.

## What Terraform creates
| Resource | Name | Notes |
|---|---|---|
| Resource group | rg-ontaix-dev-frc | tags: project, environment, owner, purpose, expires |
| Virtual network | vnet-ontaix-dev-frc | 10.40.0.0/16; snet-aks /20, snet-postgres /24 (delegated) |
| AKS | aks-ontaix-dev-frc | Free tier, 1–3 × Standard_D4s_v5, Azure CNI overlay + Cilium, OIDC issuer + workload identity, Container Insights |
| Container registry | crontaixdevfrc&lt;hash&gt; | Basic; AcrPull for the kubelet identity, no admin user |
| PostgreSQL Flexible 16 | psql-ontaix-dev-frc-&lt;hash&gt; | B_Standard_B2s, VNet-only, private DNS; password generated → Key Vault |
| Key Vault | kv-ontaix-dev-frc-&lt;hash&gt; | RBAC; secrets `postgres-admin-password`, `database-url` |
| Managed identity | id-ontaix-dev-frc | workload identity for `ontaix/ontaix-api`; Key Vault Secrets User |
| Log Analytics | log-ontaix-dev-frc | 30-day retention |
| Budget | budget-ontaix-dev-frc | €400/month; alerts at 80 % actual and 100 % forecast |

Fuseki, Valkey and NATS run inside the cluster from the Helm chart; they need no Azure resource.
Rough run cost: ~€250–350/month with one node; scale to zero by destroying the environment
between demo periods (`terraform destroy` keeps the state account).

## One-time bootstrap
1. `SUBSCRIPTION="<name or id>" bash infra/scripts/bootstrap-azure.sh` — with a signed-in Azure
   CLI as the owner. Creates the state storage, the CI identity (OIDC only, no secret), its role
   assignments, and writes `infra/scripts/ontaix-ci.env` (identifiers only).
2. `gh repo create slimfarhanigithub/ontaix --private --source . --push` (once).
3. `bash infra/scripts/bootstrap-github.sh` — with a signed-in GitHub CLI. Sets repository
   secrets (identifiers), variables and the `azure-dev` environment.
4. Open a pull request touching `infra/terraform/**` → plan. Merge to main → apply.

## Running Terraform locally (owner only)
```
cd infra/terraform/azure
az login
terraform init -backend-config="resource_group_name=$TF_STATE_RESOURCE_GROUP" \
  -backend-config="storage_account_name=$TF_STATE_STORAGE_ACCOUNT" \
  -backend-config="container_name=tfstate" -backend-config="key=azure-dev.tfstate"
TF_VAR_subscription_id=<id> terraform plan -var-file=env/dev.tfvars
```

## Security posture
- No client secret anywhere: CI uses OIDC federation; pods use workload identity; images are pulled
  with the kubelet identity; the database is VNet-only.
- The CI identity can only assign the four roles Terraform needs (RBAC Administrator with condition).
- Terraform state storage is Entra-only (shared keys disabled), versioned, soft-deleted 30 days.
