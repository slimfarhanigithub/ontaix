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
