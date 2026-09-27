#!/usr/bin/env bash
# GitHub half of the bootstrap. Run from the repository root with a signed-in GitHub CLI,
# after bootstrap-azure.sh produced infra/scripts/ontaix-ci.env:
#   bash infra/scripts/bootstrap-github.sh
# Sets repository secrets (identifiers only), variables and the azure-dev environment.
set -euo pipefail
ENV_FILE="$(cd "$(dirname "$0")" && pwd)/ontaix-ci.env"
[ -f "$ENV_FILE" ] || { echo "BLOCKED: $ENV_FILE missing — run bootstrap-azure.sh first." >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "BLOCKED: no signed-in GitHub CLI session (gh auth login)." >&2; exit 1; }
REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
set -a; . "$ENV_FILE"; set +a

for s in AZURE_CLIENT_ID AZURE_TENANT_ID AZURE_SUBSCRIPTION_ID; do
  gh secret set "$s" --repo "$REPO" --body "${!s}"
done
for v in TF_STATE_RESOURCE_GROUP TF_STATE_STORAGE_ACCOUNT TF_STATE_CONTAINER; do
  gh variable set "$v" --repo "$REPO" --body "${!v}"
done
gh api --method PUT -H "Accept: application/vnd.github+json" "repos/$REPO/environments/azure-dev" >/dev/null
echo "Configured $REPO: secrets AZURE_CLIENT_ID/TENANT_ID/SUBSCRIPTION_ID, state variables, environment azure-dev."
