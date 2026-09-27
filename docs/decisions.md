# Decision log

| # | Date | Decision | Why |
|---|---|---|---|
| 1 | 2026-09-27 | The demo file is the UI contract; the Studio must be identical to it | Built and approved screen by screen with the owner |
| 2 | 2026-09-27 | Azure, France Central, single `dev` environment | EU residency; same conventions as the owner's other projects |
| 3 | 2026-09-27 | GitHub `slimfarhanigithub/ontaix`; CI auth by OIDC federation only | No secret to leak or rotate |
| 4 | 2026-09-27 | Fresh infrastructure code (not salvaged from the earlier Slim AI repo), same naming conventions | Owner's choice |
| 5 | 2026-09-27 | AKS + managed PostgreSQL; Fuseki, Valkey, NATS in-cluster via Helm | Same chart on Azure and on plain Kubernetes proves neutrality |
| 6 | 2026-09-27 | Authorisation is Ontaix-native groups/roles; OIDC is authentication only | No dependency on Microsoft |
| 7 | 2026-09-27 | The CI identity is a user-assigned managed identity (`id-ontaix-cicd-frc`, in the Terraform state group) with GitHub OIDC federated credentials, not an Entra app registration | The owner cannot register apps in the Insight tenant; a managed identity needs only subscription rights and cannot hold a client secret |
| 8 | 2026-09-27 | The owner runs the first `terraform apply` locally; Key Vault Secrets Officer goes to two fixed principals (CI identity, owner) set in `env/dev.tfvars`; CI pins Terraform 1.15.5 | The owner's Owner role is conditioned by the tenant and cannot delegate RBAC Administrator, so CI cannot create role assignments; fixed principals keep CI plans stable after a local apply |
