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

variable "foundry_eval_deployments" {
  description = "Extra model deployments on the Foundry account for the teach extraction bake-off (chat candidates and the OCR model), keyed by deployment name. Always DataZoneStandard (EU data zone). model_format is the catalogue publisher (OpenAI, Mistral AI, DeepSeek); capacity is in the model's quota units (thousands of tokens per minute for chat models). Empty removes them."
  type = map(object({
    model_name    = string
    model_version = string
    model_format  = optional(string, "OpenAI")
    capacity      = optional(number, 50)
  }))
  default = {}

  validation {
    condition     = alltrue([for d in values(var.foundry_eval_deployments) : d.capacity >= 1 && d.capacity <= 200])
    error_message = "Each eval deployment capacity must be between 1 and 200 quota units."
  }
}

variable "foundry_claude_location" {
  description = "Region of the eval-only Foundry resource for Claude (not offered in France Central)."
  type        = string
  default     = "swedencentral"
}

variable "foundry_claude_location_short" {
  description = "Short region token of the eval-only Claude resource, used in its name."
  type        = string
  default     = "sdc"
}

variable "foundry_claude_deployments" {
  description = "Claude deployments (GlobalStandard, format Anthropic) on the eval-only Foundry resource, keyed by deployment name. Empty removes the resource."
  type = map(object({
    model_name    = string
    model_version = string
    capacity      = optional(number, 50)
  }))
  default = {}
}
