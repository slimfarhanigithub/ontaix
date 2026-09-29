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
| Key Vault | kv-ontaix-dev-frc-&lt;hash&gt; | RBAC; secrets `postgres-admin-password`, `database-url`; the optional `anthropic-api-key` is set by the owner, not by Terraform, and only when the `anthropic` provider is used (see below) |
| Azure AI Foundry | ais-ontaix-dev-frc-&lt;hash&gt; | Kind `AIServices`, S0, key authentication disabled; model deployment `gpt-6-sol` (version 2026-09-22), DataZoneStandard (EU); outputs `foundry_endpoint`, `foundry_deployment_name` |
| Managed identity | id-ontaix-dev-frc | workload identity for `ontaix/ontaix-api`; Key Vault Secrets User; Cognitive Services OpenAI User on the Foundry resource |
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

## Language Model Provider
The teach extraction model step (ADR 0008, decision row 93) calls Azure AI Foundry by default: the deployment `gpt-6-sol` (version 2026-09-22), DataZoneStandard (EU), on the Foundry resource above, billed to the Insight Azure subscription (Microsoft Azure Sponsorship). Access is keyless; no secret is needed for the default provider:

- In the cluster the API authenticates with `DefaultAzureCredential`, which resolves to the workload identity `id-ontaix-dev-frc`. Terraform assigns it the built-in role Cognitive Services OpenAI User on the Foundry resource: inference on its deployments, no management, no key listing.
- Locally the same credential resolves to the owner's `az login` session. Terraform assigns the owner the same role on the Foundry resource.
- The Foundry resource has key authentication disabled, so no Foundry API key exists.

Deployment configuration (Helm values in the cluster, the ignored `.env` locally):

| Variable | Default | Notes |
|---|---|---|
| `ONTAIX_LLM_PROVIDER` | `azure_foundry` | `azure_foundry` or `anthropic` |
| `ONTAIX_FOUNDRY_ENDPOINT` | none | Terraform output `foundry_endpoint`; not a secret |
| `ONTAIX_FOUNDRY_DEPLOYMENT` | `gpt-6-sol` | Terraform output `foundry_deployment_name` |
| `ONTAIX_LLM_MODEL` | `gpt-6-sol` | Model name recorded in `llm_call.model`; key of the price table |
| `ONTAIX_LLM_PRICE_TABLE` | none | JSON, e.g. `{"gpt-6-sol": {"inputEurPerMTok": <n>, "outputEurPerMTok": <n>}}`, from the Azure retail price of the deployment in euros; the API does not start when a provider is configured and its model has no price |
| `ONTAIX_LLM_TIMEOUT_SECONDS` | 15 | Typed and document sentences; maximum 15 |
| `ONTAIX_LLM_SPEECH_TIMEOUT_SECONDS` | 45 | Speech transcripts; maximum 45 |

Concept expansion (ADR 0009) and whole-document extraction (ADR 0010) use the same provider, endpoint, credentials and price table and run on the `deep` model profile (`ONTAIX_FOUNDRY_DEEP_*`, `ONTAIX_LLM_DEEP_REASONING_ALLOWANCE_TOKENS`); their own settings below bound size, budget and time. None of these is a secret.

| Variable | Default | Notes |
|---|---|---|
| `ONTAIX_EXPAND_MAX_NODES` | 200 | Drafts per run, 1 to 2,000; cost protection only, no depth limit |
| `ONTAIX_EXPAND_MAX_OUTPUT_TOKENS` | 32768 | |
| `ONTAIX_EXPAND_CONTEXT_LABELS` | 1000 | |
| `ONTAIX_EXPAND_TIMEOUT_SECONDS` | 120 | Maximum 300 |
| `ONTAIX_EXPAND_CALLS_PER_HOUR` | 30 | Per user |
| `ONTAIX_DOCUMENT_EXTRACTION_CHUNK_CHARS` | 10000 | Overlap is 2 sentences |
| `ONTAIX_DOCUMENT_EXTRACTION_OUTLINE_CONTEXT_NODES` | 600 | |
| `ONTAIX_DOCUMENT_EXTRACTION_MAX_NODES` | 2000 | Drafts per job, 1 to 5,000; cost protection only, no depth limit |
| `ONTAIX_DOCUMENT_EXTRACTION_MAX_TOKENS` | 1000000 | Settled tokens per job, within the tenant's monthly cap |
| `ONTAIX_DOCUMENT_EXTRACTION_MAX_CHARS` | 400000 | Largest document a job accepts |
| `ONTAIX_DOCUMENT_EXTRACTION_TIMEOUT_SECONDS` | 180 | Per call; maximum 300 |
| `ONTAIX_DOCUMENT_EXTRACTION_JOB_TIMEOUT_MINUTES` | 60 | Per job |
| `ONTAIX_DOCUMENT_EXTRACTION_JOBS_PER_HOUR` | 5 | Per user |
| `ONTAIX_DOCUMENT_EXTRACTION_MAX_ATTEMPTS` | 3 | Runner claims per job before it fails with `too_many_attempts`; 1 to 10 |
| `ONTAIX_BRANCH_APPROVE_BATCH` | 200 | Proposals per branch-approval transaction |
| `ONTAIX_BRANCH_APPROVE_MAX_ROUNDS` | 50 | Batches per branch-approval call |

OCR of scanned PDF pages (ADR 0011) calls a Mistral document model deployed on the same Foundry resource as DataZoneStandard (EU), keyless like the teach deployment. The deployment and its role assignment for the API's workload identity are added in `infra/terraform/azure` before OCR is configured; until then a scanned PDF import answers `503 unavailable`. Ontology import (ADR 0012) calls no model.

| Variable | Default | Notes |
|---|---|---|
| `ONTAIX_OCR_ENDPOINT` | value of `ONTAIX_FOUNDRY_ENDPOINT` | Unset means OCR is not configured |
| `ONTAIX_OCR_DEPLOYMENT` | `mistral-document-ai` | Or `mistral-ocr-4-0` |
| `ONTAIX_OCR_MODEL` | value of `ONTAIX_OCR_DEPLOYMENT` | Its `ONTAIX_LLM_PRICE_TABLE` entry is `{"eurPerPage": <n>}` |
| `ONTAIX_OCR_MAX_PAGES` | 100 | Image-only pages per import |
| `ONTAIX_OCR_TIMEOUT_SECONDS` | 120 | Maximum 300 |
| `ONTAIX_OCR_PAGES_PER_HOUR` | 600 | Per user or agent |
| `ONTAIX_ONTOLOGY_IMPORT_MAX_BYTES` | 20971520 | 20 MiB |
| `ONTAIX_ONTOLOGY_IMPORT_MAX_NODES` | 5000 | Drafts per import, at most 20,000; no depth limit |
| `ONTAIX_ONTOLOGY_IMPORT_PARSE_TIMEOUT_SECONDS` | 60 | Child-process wall clock |

Without `ONTAIX_FOUNDRY_ENDPOINT` the API runs normally and the teach bar uses the rule-based grammar alone (`llmOutcome` `not_configured`).

### Optional Anthropic Provider
Only when `ONTAIX_LLM_PROVIDER` is `anthropic` (with `ONTAIX_LLM_MODEL` set to an Anthropic model id and priced in the table) does the API need an Anthropic API key. It is a secret and exists in two places only:

- Azure Key Vault, secret name `anthropic-api-key`. The owner sets the value from a signed-in shell of their own; Terraform does not manage the value, so it never enters Terraform state or CI logs. The API reads it at start-up through the workload identity `id-ontaix-dev-frc`, which already holds Key Vault Secrets User.
- Local development: the ignored `.env` file, variable `ONTAIX_ANTHROPIC_API_KEY`.

The key is never in settings, API responses, events, audit entries, logs, tests, fixtures, commits or documentation, and no agent asks the owner for it in a conversation. This provider sends prompts to Anthropic outside Azure, with no EU residency guarantee (ADR 0008, Data Residency).

## Security posture
- No client secret anywhere: CI uses OIDC federation; pods use workload identity; images are pulled
  with the kubelet identity; the database is VNet-only.
- The CI identity can only assign the four roles Terraform needs (RBAC Administrator with condition).
- Terraform state storage is Entra-only (shared keys disabled), versioned, soft-deleted 30 days.
