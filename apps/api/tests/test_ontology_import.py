"""Ontology import: formats, mapping, reuse, limits, isolation and the proposal submission."""

from __future__ import annotations

import uuid
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text, update

from app.clients import db_client
from app.config import get_settings
from app.models.ontology_import.parsed_ontology import (
    PREF_LABEL,
    RDFS_LABEL,
    LabelLiteral,
    OntologyItem,
    ParsedOntology,
)
from app.models.storage.ontology_import import OntologyImport
from app.utilities.ontology_mapping import (
    MappingTarget,
    choose_label,
    map_ontology,
    safe_source,
    verb_of,
)
from tests.conftest import TenantFixture
from tests.office_files import XLSX_TYPE, xlsx
from tests.test_teach import set_settings

pytestmark = pytest.mark.asyncio(loop_scope="session")

FIXTURES = Path(__file__).parent / "fixtures" / "ontology"
PLANT = "http://example.org/plant#"


async def upload(
    client: httpx.AsyncClient,
    tenant: TenantFixture,
    name: str,
    data: bytes | None = None,
    content_type: str = "application/octet-stream",
    persona=None,
    **fields: str,
) -> httpx.Response:
    body = (FIXTURES / name).read_bytes() if data is None else data
    return await client.post(
        "/ontology-imports",
        files={"file": (name, body, content_type)},
        data={"companyId": str(tenant.company_id), **fields},
        headers=(persona or tenant.builder).headers,
    )


def by_label(result: dict) -> dict[str, tuple[dict, dict]]:
    return {
        d.get("label") or f"{d.get('aLabel')} {d['action']} {d.get('bLabel')}": (d, n)
        for d, n in zip(result["drafts"], result["notes"], strict=True)
    }


async def test_turtle_maps_classes_parents_restrictions_and_properties(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    response = await upload(client, tenant, "plant.ttl", languages="fr,en")

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["format"] == "turtle" and result["languages"] == ["fr", "en"]
    assert result["parentConceptId"] is None and result["individuals"] == "skip"
    drafts = by_label(result)
    equipment, note = drafts["Équipement"]
    assert equipment == {
        "type": "concept",
        "companyId": str(tenant.company_id),
        "label": "Équipement",
        "domainKey": "production",
        "parentId": str(tenant.root_id),
        "action": "includes",
    }
    assert note == {
        "source": PLANT + "Equipment",
        "labelLanguage": "fr",
        "depth": 1,
        "requires": [],
    }
    machine, machine_note = drafts["Machine outil"]
    assert machine["type"] == "spec" and machine["parentLabel"] == "Équipement"
    assert machine_note["labelLanguage"] == "fr-ca" and machine_note["depth"] == 2
    pump, _ = drafts["Pump"]
    assert pump["type"] == "spec" and pump["parentLabel"] == "Asset"
    assert "Pump is a Machine outil" in drafts
    assert "Sensor monitors Machine outil" in drafts
    assert "Spare Part part of Machine outil" in drafts
    concept_indexes = [i for i, d in enumerate(result["drafts"]) if d["type"] != "relation"]
    assert concept_indexes == list(range(len(concept_indexes)))
    skipped = {(s["source"], s["reason"]) for s in result["skipped"]}
    assert skipped >= {
        ("http://example.org/remote/units", "remote_import_not_fetched"),
        (PLANT + "Device", "equivalence_not_imported"),
        (PLANT + "SparePart", "unsupported_axiom"),
        (PLANT + "serialNumber", "datatype_property"),
        (PLANT + "P100", "individual_skipped"),
        (PLANT + "sameThing", "forbidden_action"),
    }


@pytest.mark.parametrize(
    ("name", "fmt", "labels"),
    [
        ("plant.rdf", "rdf_xml", {"Equipment", "Machine", "Machine driven by Equipment"}),
        (
            "plant.owx",
            "owl_xml",
            {"Plant equipment", "Control Valve", "Control Valve controls Plant equipment"},
        ),
        ("plant.jsonld", "json_ld", {"Sales", "Quote", "Order"}),
        ("plant.nt", "n_triples", {"Equipment", "Boiler"}),
        (
            "plant.obo",
            "obo",
            {
                "Equipment",
                "Heat exchanger",
                "Cooling loop",
                "Plate exchanger",
                "Heat exchanger part of Cooling loop",
            },
        ),
        ("hierarchy.csv", "csv", {"Operations", "Maintenance", "Work Order", "Inspection"}),
        (
            "levels.csv",
            "csv",
            {"Sales", "Orders", "Order Line", "Order Header", "Quotes", "Service"},
        ),
    ],
)
async def test_every_format_is_detected_and_mapped(
    client: httpx.AsyncClient, tenant: TenantFixture, name: str, fmt: str, labels: set[str]
) -> None:
    response = await upload(client, tenant, name)

    assert response.status_code == 200, response.text
    assert response.json()["format"] == fmt
    assert set(by_label(response.json())) == labels


async def test_skos_broader_and_narrower_give_includes_births(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    result = (await upload(client, tenant, "plant.jsonld")).json()

    drafts = by_label(result)
    assert (
        drafts["Quote"][0]["parentLabel"] == "Sales" and drafts["Quote"][0]["action"] == "includes"
    )
    assert drafts["Order"][0]["parentLabel"] == "Sales"
    assert ("http://example.org/sales#Order", "equivalence_not_imported") in {
        (s["source"], s["reason"]) for s in result["skipped"]
    }


async def test_hierarchy_rows_take_their_action_and_refuse_forbidden_ones(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    result = (await upload(client, tenant, "hierarchy.csv")).json()

    drafts = by_label(result)
    assert drafts["Maintenance"][0]["action"] == "runs"
    assert drafts["Inspection"][0]["action"] == "includes"
    assert drafts["Work Order"][1]["depth"] == 3
    assert {"source": "row 5", "reason": "forbidden_action", "label": "Inspection"} in result[
        "skipped"
    ]
    assert {"source": "row 6", "reason": "unknown_parent"} in result["skipped"]


async def test_an_xlsx_hierarchy_reads_its_first_sheet(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    data = xlsx(
        [
            [["Level 1", "Level 2"], ["Finance", "Invoices"], [None, "Payments"]],
            [["Level 1"], ["Ignored sheet"]],
        ]
    )

    response = await upload(client, tenant, "tree.xlsx", data, XLSX_TYPE)

    assert response.status_code == 200, response.text
    assert response.json()["format"] == "xlsx"
    assert set(by_label(response.json())) == {"Finance", "Invoices", "Payments"}


async def test_submission_creates_ontology_import_proposals_once(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    result = (await upload(client, tenant, "plant.rdf")).json()
    import_id = result["ontologyImportId"]
    everything = list(range(len(result["drafts"])))

    created = await client.post(
        f"/ontology-imports/{import_id}/proposals",
        json={"indexes": everything},
        headers=tenant.builder.headers,
    )

    assert created.status_code == 202, created.text
    proposals = created.json()
    assert [p["origin"] for p in proposals] == ["ontology_import"] * 3
    assert all(p["originDetail"] is None for p in proposals)
    assert [p["type"] for p in proposals] == ["concept", "spec", "relation"]
    assert proposals[0]["why"] == f"Imported from plant.rdf · {PLANT}Equipment"
    again = await client.post(
        f"/ontology-imports/{import_id}/proposals",
        json={"indexes": everything},
        headers=tenant.builder.headers,
    )
    assert again.status_code == 409 and again.json()["code"] == "ontology_import_submitted"
    approved = await client.post(
        f"/proposals/{proposals[0]['id']}/approve", headers=tenant.governor.headers
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["audit"]["origin"] == "ontology_import"


async def test_a_selection_must_hold_what_it_requires(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    result = (await upload(client, tenant, "plant.rdf")).json()
    import_id = result["ontologyImportId"]

    for indexes in ([1], [0, 0], [99]):
        refused = await client.post(
            f"/ontology-imports/{import_id}/proposals",
            json={"indexes": indexes},
            headers=tenant.builder.headers,
        )
        assert refused.status_code == 422, refused.text
    partial = await client.post(
        f"/ontology-imports/{import_id}/proposals",
        json={"indexes": [0]},
        headers=tenant.builder.headers,
    )
    assert partial.status_code == 202, partial.text
    assert len(partial.json()) == 1


async def test_existing_concepts_are_reused_and_known_items_skipped(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    first = (await upload(client, tenant, "hierarchy.csv")).json()
    await client.post(
        f"/ontology-imports/{first['ontologyImportId']}/proposals",
        json={"indexes": list(range(len(first["drafts"])))},
        headers=tenant.builder.headers,
    )
    data = b"label,parent\nOperation,\nMaintenance,Operation\nAudits,Maintenance\n"

    result = (await upload(client, tenant, "more.csv", data)).json()

    reasons = {s["label"]: s["reason"] for s in result["skipped"] if "label" in s}
    assert reasons == {"Operation": "already_known", "Maintenance": "already_known"}
    [audits] = result["drafts"]
    assert audits["label"] == "Audits" and "parentId" in audits
    assert result["notes"][0]["requires"] == []


async def test_get_returns_the_stored_tree_to_its_actor_only(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    result = (await upload(client, tenant, "plant.obo")).json()
    path = f"/ontology-imports/{result['ontologyImportId']}"

    mine = await client.get(path, headers=tenant.builder.headers)
    theirs = await client.get(path, headers=tenant.owner.headers)

    assert mine.status_code == 200 and mine.json() == result
    assert theirs.status_code == 404
    async with db_client.get_session_factory()() as s:
        await s.execute(
            update(OntologyImport)
            .where(OntologyImport.id == uuid.UUID(result["ontologyImportId"]))
            .values(
                created_at=text("now() - interval '25 hours'"),
                expires_at=text("now() - interval '1 hour'"),
            )
        )
        await s.commit()
    expired = await client.get(path, headers=tenant.builder.headers)
    assert expired.status_code == 410 and expired.json()["code"] == "ontology_import_expired"
    submit = await client.post(
        f"{path}/proposals", json={"indexes": [0]}, headers=tenant.builder.headers
    )
    assert submit.status_code == 410


@pytest.mark.parametrize(
    ("name", "status"),
    [("entities.rdf", 415), ("xxe.rdf", 415), ("remote-context.jsonld", 422)],
)
async def test_dtds_entities_and_remote_contexts_are_refused_and_nothing_stored(
    client: httpx.AsyncClient, tenant: TenantFixture, name: str, status: int
) -> None:
    response = await upload(client, tenant, name)

    assert response.status_code == status, response.text
    assert await _stored(tenant) == 0


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("plant.ttl", b"<?xml version='1.0'?><rdf:RDF xmlns:rdf='x'/>"),
        ("plant.nt", (FIXTURES / "plant.ttl").read_bytes()),
        ("plant.exe", b"MZ"),
        ("plant.xlsx", b"PK\x03\x04 not a workbook"),
    ],
)
async def test_the_detected_format_must_agree_with_the_declared_one(
    client: httpx.AsyncClient, tenant: TenantFixture, name: str, data: bytes
) -> None:
    response = await upload(client, tenant, name, data)

    assert response.status_code == 415, response.text


async def test_limits_refuse_the_whole_import(
    client: httpx.AsyncClient, tenant: TenantFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ontology_import_max_nodes", 2)
    too_many = await upload(client, tenant, "plant.rdf")
    assert too_many.status_code == 413, too_many.text

    monkeypatch.setattr(get_settings(), "ontology_import_max_bytes", 100)
    too_large = await upload(client, tenant, "plant.rdf")
    assert too_large.status_code == 413, too_large.text

    monkeypatch.setattr(get_settings(), "ontology_import_max_bytes", 20 * 1024 * 1024)
    monkeypatch.setattr(get_settings(), "ontology_import_parse_timeout_seconds", 0.01)
    too_slow = await upload(client, tenant, "plant.rdf")
    assert too_slow.status_code == 413, too_slow.text
    assert await _stored(tenant) == 0


async def test_rules_of_the_channel_scope_and_parent(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    outsider = await upload(client, tenant, "plant.rdf", persona=tenant.outsider)
    assert outsider.status_code == 403
    unknown = await upload(client, tenant, "plant.rdf", parentConceptId=str(uuid.uuid4()))
    assert unknown.status_code == 404
    bad_domain = await upload(client, tenant, "plant.rdf", domainKey="nowhere")
    assert bad_domain.status_code == 422
    bad_languages = await upload(client, tenant, "plant.rdf", languages="en fr")
    assert bad_languages.status_code == 422
    pending = await client.post(
        "/proposals",
        json={
            "type": "concept",
            "companyId": str(tenant.company_id),
            "parentId": str(tenant.root_id),
            "label": "Pending Area",
            "domainKey": "production",
        },
        headers=tenant.builder.headers,
    )
    under_pending = await upload(
        client, tenant, "plant.rdf", parentConceptId=pending.json()["conceptId"]
    )
    assert under_pending.status_code == 409 and under_pending.json()["code"] == "concept_pending"
    await set_settings(tenant, import_docs=False)
    disabled = await upload(client, tenant, "plant.rdf")
    assert disabled.status_code == 409 and disabled.json()["code"] == "channel_disabled"


async def test_individuals_become_instances_when_asked(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    result = (await upload(client, tenant, "plant.ttl", individuals="as_concepts")).json()

    instance, note = by_label(result)["Pump P100"]
    assert instance["type"] == "concept" and instance["action"] == "has instance"
    assert instance["parentLabel"] == "Pump" and note["depth"] == 3


async def test_labels_follow_the_language_preference() -> None:
    labels = {
        RDFS_LABEL: [
            LabelLiteral("Machine", "en"),
            LabelLiteral("Maschine", "de"),
            LabelLiteral("Machine outil", "fr-ca"),
            LabelLiteral("Plain machine"),
        ],
        PREF_LABEL: [LabelLiteral("   ")],
    }
    assert choose_label(labels, "machineX", ("fr",)) == ("Machine outil", "fr-ca")
    assert choose_label(labels, "machineX", ("de", "en")) == ("Maschine", "de")
    assert choose_label(labels, "machineX", ("it",)) == ("Plain machine", None)
    assert choose_label({}, "purchase_orderLine", ("en",)) == ("purchase order Line", None)
    assert verb_of("isPartOf") == "is part of"


async def test_sources_hide_nothing_and_cycles_are_broken() -> None:
    assert (
        safe_source("http://x/\u202eevil\u200b\u2028") == "http://x/%E2%80%AEevil%E2%80%8B%E2%80%A8"
    )
    parsed = ParsedOntology(format="turtle")
    for name, parent in (("a", "c"), ("b", "a"), ("c", "b")):
        item = OntologyItem(source=f"http://x/{name}", local_name=name)
        item.parents.append((f"http://x/{parent}", "spec"))
        parsed.items.append(item)
    root = uuid.uuid4()
    target = MappingTarget(
        uuid.uuid4(), root, None, frozenset({"production"}), None, ("en",), "skip", 100
    )

    tree = map_ontology(parsed, target, [], set())

    assert {"source": "http://x/a", "reason": "cycle", "label": "A"} in tree.skipped
    assert [d["label"] for d in tree.drafts] == ["A", "B", "C"]
    assert tree.drafts[0]["parentId"] == str(root)


async def _stored(tenant: TenantFixture) -> int:
    async with db_client.get_session_factory()() as s:
        return int(
            await s.scalar(
                text("SELECT count(*) FROM ontaix.ontology_import WHERE tenant_id = :t"),
                {"t": tenant.tenant_id},
            )
            or 0
        )
