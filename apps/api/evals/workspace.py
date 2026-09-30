"""A scratch tenant for one bake-off case, driven through the real API in process.

Each case gets its own tenant in the scratch database: a builder who teaches and a governor who
approves, the case's company as the home company, and the case's pre-existing concepts proposed
and approved. The builder then calls `POST /teach/parse` exactly as the Studio does, one session
for the whole case, and submits each result's drafts before the next unit, so later sentences
resolve against what earlier ones introduced. A whole-document reading starts the extraction
job as the Studio's import dialog does, runs the API's own job runner in process until the job
ends, reads its result and proposes every draft of it.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy import text

from app.clients import db_client
from app.models.storage.base import RoleName, ScopeKind
from app.repositories import (
    app_user_repository,
    group_member_repository,
    group_role_repository,
    tenant_repository,
    tenant_settings_repository,
    user_group_repository,
    view_state_repository,
)
from app.services import company_service, document_extraction_runner_service
from app.services.ontology_view_service import load_view
from evals.scoring import normalise_label
from evals.teach_case import TeachCase

DEV_ISSUER = "dev"
# The tenant's monthly token cap never stops a bake-off; the per-call bounds still apply.
MONTHLY_TOKEN_CAP = 1_000_000_000
JOB_STATES_IN_PROGRESS = ("queued", "running")
JOB_POLL_SECONDS = 0.2


@dataclass
class UnitResult:
    """One `POST /teach/parse` and the submission of its drafts."""

    text: str
    status: int
    wall_ms: int
    extractor: str | None = None
    llm_outcome: str | None = None
    degraded: bool = False
    outcome: str | None = None
    unresolved: list[dict[str, Any]] = field(default_factory=list)
    drafts: list[dict[str, Any]] = field(default_factory=list)
    statements: list[str] = field(default_factory=list)
    submitted: int = 0
    submit_error: str | None = None
    error: str | None = None


class SeedError(Exception):
    """The case's tenant or its pre-existing concepts could not be set up."""


class Workspace:
    def __init__(self, client: httpx.AsyncClient, case: TeachCase) -> None:
        self._client = client
        self.case = case
        self.session_id = uuid.uuid4()
        self.tenant_id: uuid.UUID | None = None
        self.company_id: uuid.UUID | None = None
        self.root_id: uuid.UUID | None = None
        self._builder: dict[str, str] = {}
        self._governor: dict[str, str] = {}

    async def open(self) -> None:
        slug = f"eval-{uuid.uuid4().hex[:12]}"
        async with db_client.get_session_factory()() as s:
            tenant = await tenant_repository.create(s, slug, f"Bake-off {slug}")
            await tenant_settings_repository.create(s, tenant.id)
            await view_state_repository.create(s, tenant.id)
            users = {}
            for role, grant in (("builder", RoleName.BUILDER), ("governor", RoleName.GOVERNOR)):
                subject = f"{role}@{slug}.eval"
                user = await app_user_repository.create(
                    s,
                    tenant_id=tenant.id,
                    issuer=DEV_ISSUER,
                    subject=subject,
                    email=subject,
                    name=role.title(),
                    department=None,
                    company_id=None,
                )
                group = await user_group_repository.create(s, tenant.id, f"{role} group", "")
                await group_member_repository.add(s, tenant.id, group.id, user.id)
                await group_role_repository.create(
                    s,
                    tenant_id=tenant.id,
                    group_id=group.id,
                    role=grant,
                    scope_kind=ScopeKind.TENANT,
                    scope_company_id=None,
                    scope_domain_key=None,
                )
                users[role] = subject
            view = await load_view(s, tenant.id)
            company = await company_service.add_company(
                s, view, self.case.company, "", is_home=True
            )
            root = view.root_of(company.id)
            if root is None:
                raise SeedError("the company has no root concept")
            await s.execute(
                text(
                    "UPDATE ontaix.tenant_settings SET llm_monthly_token_cap = :cap"
                    " WHERE tenant_id = :tenant_id"
                ),
                {"cap": MONTHLY_TOKEN_CAP, "tenant_id": tenant.id},
            )
            await s.commit()
        self.tenant_id, self.company_id, self.root_id = tenant.id, company.id, root.id
        self._builder = {"X-Ontaix-User": users["builder"]}
        self._governor = {"X-Ontaix-User": users["governor"]}
        await self._seed_existing()

    async def parse(self, body: dict[str, Any]) -> UnitResult:
        """One teach parse in the case's session; the drafts are submitted right after."""
        request = {"companyId": str(self.company_id), "sessionId": str(self.session_id), **body}
        started = time.monotonic()
        response = await self._client.post("/teach/parse", json=request, headers=self._builder)
        wall_ms = int((time.monotonic() - started) * 1000)
        shown = body.get("text") or f"importRef {body.get('importRef')}"
        if response.status_code != 200:
            return UnitResult(shown, response.status_code, wall_ms, error=response.text[:300])
        data = response.json()
        unit = UnitResult(
            text=shown,
            status=200,
            wall_ms=wall_ms,
            extractor=data.get("extractor"),
            llm_outcome=data.get("llmOutcome"),
            degraded=bool(data.get("degraded")),
            outcome=data.get("outcome"),
            unresolved=data.get("unresolved") or [],
            drafts=data.get("drafts") or [],
            statements=data.get("statements") or [],
        )
        if unit.drafts:
            submitted = await self._client.post(
                "/proposals/batch", json={"drafts": unit.drafts}, headers=self._builder
            )
            if submitted.status_code == 202:
                unit.submitted = len(submitted.json())
            else:
                unit.submit_error = f"{submitted.status_code} {submitted.text[:300]}"
        return unit

    async def extract_whole(self, import_id: str) -> tuple[UnitResult, dict[str, Any]]:
        """One whole-document extraction of a stored import, run to its end in process, with
        its drafts proposed: the unit and the job's own figures (chunks, outline nodes, tokens).
        The job runs alone: the runner claims the oldest waiting job of any tenant, so two
        readings at once would record each other's calls."""
        started = time.monotonic()
        shown = f"whole document (import {import_id})"
        response = await self._client.post(
            f"/import/{import_id}/extraction",
            json={"companyId": str(self.company_id)},
            headers=self._builder,
        )
        if response.status_code != 202:
            wall_ms = int((time.monotonic() - started) * 1000)
            return UnitResult(shown, response.status_code, wall_ms, error=response.text[:300]), {}
        job = response.json()
        while job["state"] in JOB_STATES_IN_PROGRESS:
            ran = await document_extraction_runner_service.run_once()
            job = await self._job(job["id"])
            if not ran and job["state"] in JOB_STATES_IN_PROGRESS:
                await asyncio.sleep(JOB_POLL_SECONDS)
        wall_ms = int((time.monotonic() - started) * 1000)
        figures = {
            "chunks": job["chunks"],
            "outlineNodes": job["outlineNodes"],
            "tokensUsed": job["tokensUsed"],
            "degraded": job["degraded"],
            "failureReason": job["failureReason"],
        }
        unit = UnitResult(
            text=shown,
            status=200,
            wall_ms=wall_ms,
            extractor="llm",
            llm_outcome="used" if job["state"] == "succeeded" else job["failureReason"],
            degraded=bool(job["degraded"]),
        )
        if job["state"] != "succeeded":
            unit.outcome = "not_understood"
            unit.error = f"{job['state']}: {job['failureReason']}"
            return unit, figures
        result = await self._client.get(f"/extractions/{job['id']}/result", headers=self._builder)
        if result.status_code != 200:
            unit.error = f"result {result.status_code} {result.text[:300]}"
            return unit, figures
        body = result.json()
        unit.drafts = body.get("drafts") or []
        unit.unresolved = body.get("unresolved") or []
        unit.outcome = "understood" if unit.drafts else "not_understood"
        if unit.drafts:
            submitted = await self._client.post(
                f"/extractions/{job['id']}/proposals",
                json={"indexes": list(range(len(unit.drafts)))},
                headers=self._builder,
            )
            if submitted.status_code == 202:
                unit.submitted = len(submitted.json())
            else:
                unit.submit_error = f"{submitted.status_code} {submitted.text[:300]}"
        return unit, figures

    async def _job(self, job_id: str) -> dict[str, Any]:
        response = await self._client.get(f"/extractions/{job_id}", headers=self._builder)
        if response.status_code != 200:
            raise SeedError(f"extraction job unreadable: {response.status_code} {response.text}")
        return response.json()

    async def upload(self, file_name: str, data: bytes) -> tuple[str, int]:
        """Stores a document as an import; returns its id and its sentence count."""
        response = await self._client.post(
            "/import/sentences", files={"file": (file_name, data)}, headers=self._builder
        )
        if response.status_code != 200:
            raise SeedError(f"import refused: {response.status_code} {response.text[:300]}")
        body = response.json()
        return body["importId"], len(body["sentences"])

    async def labels(self) -> dict[str, str]:
        """Every concept id of the tenant (approved and pending) with its label."""
        async with db_client.get_session_factory()() as s:
            view = await load_view(s, self.tenant_id)
            return {str(c.id): c.label for c in view.concepts.values()}

    async def _seed_existing(self) -> None:
        if not self.case.existing:
            return
        root_key = normalise_label(self.case.company)
        drafts = []
        for c in self.case.existing:
            draft: dict[str, Any] = {
                "type": "concept",
                "companyId": str(self.company_id),
                "label": c.label,
                "domainKey": c.domain,
                "action": c.action,
            }
            if normalise_label(c.parent) == root_key:
                draft["parentId"] = str(self.root_id)
            else:
                draft["parentLabel"] = c.parent
            drafts.append(draft)
        created = await self._client.post(
            "/proposals/batch", json={"drafts": drafts}, headers=self._builder
        )
        if created.status_code != 202:
            raise SeedError(f"existing concepts refused: {created.status_code} {created.text}")
        approved = await self._client.post("/proposals/approve-all", headers=self._governor)
        if approved.status_code != 200:
            raise SeedError(f"approving existing concepts failed: {approved.status_code}")
