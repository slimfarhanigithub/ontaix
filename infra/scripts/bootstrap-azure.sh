#!/usr/bin/env bash
# One-time Azure foundation for Ontaix. Run once by the owner with a signed-in Azure CLI:
#   bash infra/scripts/bootstrap-azure.sh
# Idempotent: re-running converges to the same state. Never creates, reads or prints a secret.
#
# Creates or ensures:
#   - resource providers used by infra/terraform/azure;
#   - the environment resource group and the Terraform state resource group;
#   - a Terraform state storage account (Entra-only access, TLS 1.2, versioning, soft delete);
#   - the CI identity: user-assigned managed identity id-ontaix-cicd-frc in the state resource
#     group (it carries no secret or certificate and needs no Entra directory rights to create),
#     trusted by GitHub OIDC for: the azure-dev environment, the main branch, and pull requests;
#   - role assignments for the CI identity: Contributor on the environment group, blob access to
#     the state container, and Role Based Access Control Administrator limited by condition to the
#     roles Terraform assigns;
#   - infra/scripts/ontaix-ci.env holding identifiers only (client id, tenant id, subscription id,
#     state account) for bootstrap-github.sh.
set -euo pipefail
export MSYS_NO_PATHCONV=1

PROJECT="ontaix"
LOCATION="${LOCATION:-francecentral}"
LOCATION_SHORT="${LOCATION_SHORT:-frc}"
ENVIRONMENT="${ENVIRONMENT:-dev}"
GITHUB_REPO="${GITHUB_REPO:-slimfarhanigithub/ontaix}"
SUBSCRIPTION="${SUBSCRIPTION:?Set SUBSCRIPTION to the subscription name or id}"

ENV_RG="rg-${PROJECT}-${ENVIRONMENT}-${LOCATION_SHORT}"
STATE_RG="rg-${PROJECT}-tfstate-${LOCATION_SHORT}"
STATE_CONTAINER="tfstate"
CI_IDENTITY="id-${PROJECT}-cicd-${LOCATION_SHORT}"
OIDC_ISSUER="https://token.actions.githubusercontent.com"
OIDC_AUDIENCE="api://AzureADTokenExchange"
OUT_FILE="$(cd "$(dirname "$0")" && pwd)/ontaix-ci.env"

blocked() { echo "BLOCKED: $*" >&2; exit 1; }
GUID_RE='^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'

az account show --output none 2>/dev/null || blocked "no signed-in Azure CLI session."
az account set --subscription "$SUBSCRIPTION"
SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
TENANT_ID="$(az account show --query tenantId -o tsv)"
OWNER_OBJECT_ID="$(az ad signed-in-user show --query id -o tsv)"
echo "Subscription $SUBSCRIPTION_ID, tenant $TENANT_ID"

echo "Registering resource providers"
for ns in Microsoft.ContainerService Microsoft.ContainerRegistry Microsoft.DBforPostgreSQL \
          Microsoft.KeyVault Microsoft.OperationalInsights Microsoft.OperationsManagement \
          Microsoft.Insights Microsoft.Consumption Microsoft.Network Microsoft.ManagedIdentity \
          Microsoft.Compute Microsoft.Storage; do
  az provider register --namespace "$ns" --output none
done

echo "Ensuring resource groups"
ensure_group() {
  local group="$1"; shift
  if [ "$(az group exists --name "$group")" = "true" ]; then
    az tag update --resource-id "$(az group show --name "$group" --query id -o tsv)" \
      --operation Merge --tags "$@" --output none
  else
    az group create --name "$group" --location "$LOCATION" --tags "$@" --output none
  fi
}
ensure_group "$ENV_RG"   project=$PROJECT environment=$ENVIRONMENT owner=slim.farhani purpose=demo
ensure_group "$STATE_RG" project=$PROJECT purpose=terraform-state owner=slim.farhani
ENV_RG_ID="$(az group show --name "$ENV_RG" --query id -o tsv)"

echo "Ensuring Terraform state storage"
UNIQUE="$(printf '%s' "${SUBSCRIPTION_ID}-${STATE_RG}" | sha1sum | cut -c1-5)"
STATE_ACCOUNT="st${PROJECT}tfstate${UNIQUE}"
if ! az storage account show --name "$STATE_ACCOUNT" --resource-group "$STATE_RG" --output none 2>/dev/null; then
  az storage account create --name "$STATE_ACCOUNT" --resource-group "$STATE_RG" --location "$LOCATION" \
    --sku Standard_LRS --kind StorageV2 --min-tls-version TLS1_2 --https-only true \
    --allow-blob-public-access false --allow-shared-key-access false \
    --tags project=$PROJECT purpose=terraform-state --output none
fi
az storage account blob-service-properties update --account-name "$STATE_ACCOUNT" --resource-group "$STATE_RG" \
  --enable-versioning true --enable-delete-retention true --delete-retention-days 30 --output none
STATE_ACCOUNT_ID="$(az storage account show --name "$STATE_ACCOUNT" --resource-group "$STATE_RG" --query id -o tsv)"
# The owner needs data-plane access to create the container and to run Terraform locally.
az role assignment create --assignee-object-id "$OWNER_OBJECT_ID" --assignee-principal-type User \
  --role "Storage Blob Data Contributor" --scope "$STATE_ACCOUNT_ID" --output none 2>/dev/null || true
# Data-plane role assignments take up to a few minutes to propagate; retry the container creation.
for attempt in $(seq 1 12); do
  if az storage container create --name "$STATE_CONTAINER" --account-name "$STATE_ACCOUNT" --auth-mode login --output none 2>/dev/null; then
    break
  fi
  [ "$attempt" -lt 12 ] || blocked "could not create the state container after waiting for role propagation."
  echo "  waiting for role propagation ($attempt/12)"; sleep 15
done

echo "Ensuring the CI identity $CI_IDENTITY (OIDC only)"
# A managed identity has no client secret or certificate by construction, and lives in the state
# group so destroying the environment group never removes CI's ability to recreate it.
if ! az identity show --name "$CI_IDENTITY" --resource-group "$STATE_RG" --output none 2>/dev/null; then
  az identity create --name "$CI_IDENTITY" --resource-group "$STATE_RG" --location "$LOCATION" \
    --tags project=$PROJECT purpose=cicd owner=slim.farhani --output none
fi
APP_ID="$(az identity show --name "$CI_IDENTITY" --resource-group "$STATE_RG" --query clientId -o tsv)"
SP_OBJECT_ID="$(az identity show --name "$CI_IDENTITY" --resource-group "$STATE_RG" --query principalId -o tsv)"
[[ "$APP_ID" =~ $GUID_RE ]] || blocked "unparseable clientId '$APP_ID'."
[[ "$SP_OBJECT_ID" =~ $GUID_RE ]] || blocked "unparseable principalId '$SP_OBJECT_ID'."

# Managed identities reject concurrent federated-credential writes; these run one at a time.
ensure_trust() {
  local name="$1" subject="$2" current
  current="$(az identity federated-credential list --identity-name "$CI_IDENTITY" --resource-group "$STATE_RG" \
    --query "[?name=='$name'].subject | [0]" -o tsv)"
  if [ -z "$current" ]; then
    echo "Creating federated credential $name"
    az identity federated-credential create --name "$name" --identity-name "$CI_IDENTITY" \
      --resource-group "$STATE_RG" --issuer "$OIDC_ISSUER" --subject "$subject" \
      --audiences "$OIDC_AUDIENCE" --output none
  elif [ "$current" != "$subject" ]; then
    echo "Updating federated credential $name"
    az identity federated-credential update --name "$name" --identity-name "$CI_IDENTITY" \
      --resource-group "$STATE_RG" --issuer "$OIDC_ISSUER" --subject "$subject" \
      --audiences "$OIDC_AUDIENCE" --output none
  fi
}
# GitHub's OIDC subject names the repository as owner@<owner id>/name@<repo id> once the repository
# exists, so a renamed or re-created repository with the same name is not trusted.
SUBJECT_REPO="$GITHUB_REPO"
if REPO_IDS="$(gh api "repos/$GITHUB_REPO" --jq '"\(.owner.id) \(.id)"' 2>/dev/null)"; then
  read -r OWNER_ID REPO_ID <<<"$REPO_IDS"
  SUBJECT_REPO="${GITHUB_REPO%%/*}@${OWNER_ID}/${GITHUB_REPO#*/}@${REPO_ID}"
fi
ensure_trust github-azure-dev   "repo:${SUBJECT_REPO}:environment:azure-dev"
ensure_trust github-main        "repo:${SUBJECT_REPO}:ref:refs/heads/main"
ensure_trust github-pull-request "repo:${SUBJECT_REPO}:pull_request"

echo "Granting roles to the CI identity"
assign() { az role assignment create --assignee-object-id "$SP_OBJECT_ID" --assignee-principal-type ServicePrincipal "$@" --output none 2>/dev/null || true; }
assign --role Contributor --scope "$ENV_RG_ID"
assign --role "Storage Blob Data Contributor" --scope "$STATE_ACCOUNT_ID/blobServices/default/containers/$STATE_CONTAINER"
# Terraform assigns exactly these roles: AcrPull, Network Contributor, Key Vault Secrets Officer,
# Key Vault Secrets User, Azure Kubernetes Service RBAC Cluster Admin. The condition prevents the
# CI identity from granting anything else. The subscription's conditioned Owner cannot delegate
# this role, so the assignment below is refused (and swallowed): role assignments are then made
# by the owner's local `terraform apply`, and a CI apply that adds one fails until then.
ALLOWED='{7f951dda-4ed3-4680-a7ca-43fe172d538d, 4d97b98b-1d4f-4787-a291-c67834d212e7, b86a8fe4-44ce-4948-aee5-eccb2c155cd7, 4633458b-17de-408a-b874-0445c86b69e6, b1ff04bb-8a4e-4dc4-8eb5-8693973ce19b}'
CONDITION="((!(ActionMatches{'Microsoft.Authorization/roleAssignments/write'})) OR (@Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals $ALLOWED)) AND ((!(ActionMatches{'Microsoft.Authorization/roleAssignments/delete'})) OR (@Resource[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals $ALLOWED))"
assign --role "Role Based Access Control Administrator" --scope "$ENV_RG_ID" --condition "$CONDITION" --condition-version 2.0

cat > "$OUT_FILE" <<ENV
# Identifiers only — no secret. Consumed by infra/scripts/bootstrap-github.sh. Safe to commit.
AZURE_CLIENT_ID=$APP_ID
AZURE_TENANT_ID=$TENANT_ID
AZURE_SUBSCRIPTION_ID=$SUBSCRIPTION_ID
TF_STATE_RESOURCE_GROUP=$STATE_RG
TF_STATE_STORAGE_ACCOUNT=$STATE_ACCOUNT
TF_STATE_CONTAINER=$STATE_CONTAINER
ENV
echo "Done. Wrote $OUT_FILE"
cat "$OUT_FILE"
