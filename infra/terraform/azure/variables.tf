variable "subscription_id" {
  description = "Azure subscription the environment is deployed into."
  type        = string
}

variable "location" {
  description = "Azure region for all regional resources."
  type        = string
  default     = "francecentral"
}

variable "location_short" {
  description = "Short region token used in resource names."
  type        = string
  default     = "frc"
}

variable "project" {
  description = "Project token used in resource names and tags."
  type        = string
  default     = "ontaix"
}

variable "environment" {
  description = "Environment name (dev, demo, ...)."
  type        = string
  default     = "dev"
}

variable "owner" {
  description = "Value of the owner tag."
  type        = string
  default     = "slim.farhani"
}

variable "owner_email" {
  description = "Recipient of budget alerts."
  type        = string
}

variable "ci_principal_id" {
  description = "Object (principal) id of the CI managed identity id-ontaix-cicd-frc; granted Key Vault Secrets Officer."
  type        = string
}

variable "owner_principal_id" {
  description = "Entra object id of the owner; granted Key Vault Secrets Officer for local Terraform runs."
  type        = string
}

variable "expires_on" {
  description = "Value of the expires tag, as an ISO date. Reviewed monthly."
  type        = string
}

variable "monthly_budget_eur" {
  description = "Monthly budget for the resource group. Alerts at 80 % and 100 %."
  type        = number
  default     = 400
}

# Network
variable "vnet_cidr" {
  type    = string
  default = "10.40.0.0/16"
}

variable "aks_subnet_cidr" {
  type    = string
  default = "10.40.0.0/20"
}

variable "postgres_subnet_cidr" {
  type    = string
  default = "10.40.16.0/24"
}

# AKS
variable "aks_kubernetes_version" {
  description = "Kubernetes minor version. Null takes the region default."
  type        = string
  default     = null
}

variable "aks_node_vm_size" {
  description = "VM size of the single system+workload node pool."
  type        = string
  default     = "Standard_D4s_v5"
}

variable "aks_node_count_min" {
  type    = number
  default = 1
}

variable "aks_node_count_max" {
  type    = number
  default = 3
}

variable "aks_local_accounts_disabled" {
  description = "Refuse the cluster's local accounts (the static cluster-admin certificate of `az aks get-credentials --admin`). Set true only after the owner's kubelogin access and a green deploy run are verified; the cut-over is in docs/provisioning.md, Cluster Access."
  type        = bool
  default     = false
}

# PostgreSQL
variable "postgres_version" {
  type    = string
  default = "16"
}

variable "postgres_sku_name" {
  type    = string
  default = "B_Standard_B2s"
}

variable "postgres_storage_mb" {
  type    = number
  default = 32768
}

variable "postgres_admin_login" {
  description = "Administrator login. The password is generated and stored in Key Vault, never supplied."
  type        = string
  default     = "ontaix_admin"
}

variable "postgres_database" {
  type    = string
  default = "ontaix"
}

# Workload identity
variable "workload_namespace" {
  description = "Kubernetes namespace of the Ontaix release."
  type        = string
  default     = "ontaix"
}

variable "workload_service_account" {
  description = "Kubernetes service account that federates to the workload identity."
  type        = string
  default     = "ontaix-api"
}

# Azure AI Foundry
variable "foundry_public_network_access_enabled" {
  description = "Whether the Foundry endpoint is reachable from the public internet. Authentication stays Entra ID only."
  type        = bool
  default     = true
}

variable "foundry_deployment_name" {
  description = "Name of the model deployment; the API passes it as the model/deployment id."
  type        = string
  default     = "gpt-6-sol"
}

variable "foundry_model_name" {
  description = "OpenAI model name in the Foundry catalogue."
  type        = string
  default     = "gpt-6-sol"
}

variable "foundry_model_version" {
  description = "Model version string as listed by the Foundry catalogue for the region."
  type        = string
  default     = "2026-09-22"
}

variable "foundry_deployment_sku" {
  description = "Deployment SKU. DataZoneStandard keeps processing inside the EU data zone."
  type        = string
  default     = "DataZoneStandard"
}

variable "foundry_deployment_capacity" {
  description = "Deployment capacity in units of 1,000 tokens per minute."
  type        = number
  default     = 100
}

variable "foundry_claude_location" {
  description = "Region of the Foundry resource for Claude (not offered in France Central)."
  type        = string
  default     = "swedencentral"
}

variable "foundry_claude_location_short" {
  description = "Short region token of the Claude resource, used in its name."
  type        = string
  default     = "sdc"
}

variable "foundry_claude_deployments" {
  description = "Claude deployments on the Claude resource, keyed by model name (also the deployment name the API sends): catalogue version and GlobalStandard capacity."
  type = map(object({
    model_version = string
    capacity      = number
  }))
  default = {}
}

variable "foundry_claude_organization" {
  description = "Organisation attested to Anthropic on each Claude deployment: legal name, ISO 3166-1 alpha-2 country code, and lowercase industry (technology, finance, healthcare, education, retail, manufacturing, government, media, other)."
  type = object({
    name         = string
    country_code = string
    industry     = string
  })
  default = null

  validation {
    condition     = length(var.foundry_claude_deployments) == 0 || var.foundry_claude_organization != null
    error_message = "Claude deployments need foundry_claude_organization."
  }
}
