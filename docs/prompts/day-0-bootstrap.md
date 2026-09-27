# Day 0 — bootstrap prompt for Claude Code (paste into the Claude Code panel in VS Code)

You are the platform agent for Ontaix. Read CLAUDE.md and docs/provisioning.md first, then do the
one-time bootstrap from this folder, step by step, showing me each command's output before the next.

Rules: never print, ask for, or store a secret; identifiers (client id, tenant id, subscription id)
are fine. If any script prints BLOCKED or a command fails, stop and show me the error. Never edit
anything under reference/. Do not create resources with the portal or ad-hoc az commands — only the
scripts and Terraform in this repository.

Steps:
1. Check `az account show` and `gh auth status`. If Azure is not signed in, run `az login` and wait
   for me to complete it in the browser (account slim.farhani@insight.com, directory
   "Insight technology solution"). Then confirm the subscription "Microsoft Azure Sponsorship" is visible.
2. Run: SUBSCRIPTION="Microsoft Azure Sponsorship" bash infra/scripts/bootstrap-azure.sh
   Show me infra/scripts/ontaix-ci.env when it exists.
3. Initialise git on branch main, commit everything with message "chore: Ontaix foundation", then
   create the private repository slimfarhanigithub/ontaix with gh and push.
4. Run: bash infra/scripts/bootstrap-github.sh
5. Trigger the infra workflow (`gh workflow run infra.yml`), watch it (`gh run watch`), and report
   the Terraform apply result and the outputs (resource group, AKS name, ACR login server, Key Vault
   name, Postgres FQDN). If the plan shows anything other than creations, stop and show me.
6. Delete the folder _to_delete/ and finish with a short summary of what now exists in Azure and
   what it costs per month.
