"""Reads the named Key Vault secrets with the pod's identity and writes them as `.env` files,
one per container that reads them: the API's file holds the API's own connection, the file of
the migration step, the login step and the admin terminal holds the schema owner's. Each file is
mounted into its container alone, so the API process never sees the owner's URL. Runs in the API
image, which carries azure-identity and httpx, with the pod's workload identity and nothing else.
A value is never printed or logged; a failure names the secret and the HTTP status only.

Environment: KEY_VAULT_NAME, KEY_VAULT_FILES (JSON object: output file to an object of
environment variable to secret name).
"""

from __future__ import annotations

import json
import os
import sys

import httpx
from azure.identity import WorkloadIdentityCredential

KEY_VAULT_API_VERSION = "7.4"
KEY_VAULT_SCOPE = "https://vault.azure.net/.default"


def dotenv_line(name: str, value: str) -> str:
    """One `NAME='value'` line, quoted the way python-dotenv reads it back."""
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"{name}='{escaped}'\n"


def main() -> int:
    vault = os.environ["KEY_VAULT_NAME"]
    files: dict[str, dict[str, str]] = json.loads(os.environ["KEY_VAULT_FILES"])
    # The pod's projected token only (AZURE_CLIENT_ID, AZURE_TENANT_ID and
    # AZURE_FEDERATED_TOKEN_FILE, injected by the workload identity webhook); no other source.
    token = WorkloadIdentityCredential().get_token(KEY_VAULT_SCOPE).token
    values: dict[str, str] = {}
    with httpx.Client(
        base_url=f"https://{vault}.vault.azure.net",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    ) as client:
        for secret in sorted({name for mapping in files.values() for name in mapping.values()}):
            response = client.get(
                f"/secrets/{secret}", params={"api-version": KEY_VAULT_API_VERSION}
            )
            if response.status_code != 200:
                print(
                    f"{secret}: Key Vault {vault} answered {response.status_code}", file=sys.stderr
                )
                return 1
            values[secret] = response.json()["value"]
    for output, mapping in files.items():
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            handle.writelines(
                dotenv_line(variable, values[secret]) for variable, secret in mapping.items()
            )
        print(f"{len(mapping)} secret(s) from {vault} written to {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
