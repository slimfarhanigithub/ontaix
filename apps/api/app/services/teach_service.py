"""`POST /teach/parse`: one sentence to intents and proposal drafts, writing nothing to the model.

The sentence is typed text, a speech transcript, or a stored import sentence cited by
`importRef`, whose text is read from the import. Every path runs the same grammar and resolves
the names it finds against the company's current concepts, pending ones included; a name that
resolves to nothing becomes a proposed new cell, never a silent creation.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller
from app.models.api.origin import ImportRef
from app.models.api.teach import Intent, TeachRequest, TeachResult
from app.models.storage.concept import Concept
from app.services import import_service
from app.services.ontology_view_service import OntologyView, load_view
from app.services.rate_limit_service import Budget, charge
from app.utilities.channels import (
    ensure_import_allowed,
    ensure_live_teaching_allowed,
    ensure_speech_allowed,
)
from app.utilities.permissions import can_propose_anywhere, can_read
from app.utilities.problems import forbidden, not_found
from app.utilities.teach_parser import content_words, domain_prefix, singular, title, understand

logger = logging.getLogger(__name__)

NOT_UNDERSTOOD = (
    "Try “<subject> <action> <object>”, “A is a B”, or “A that … is a B”. "
    "Start with “In quality, …” to choose the domain product."
)
DEFAULT_DOMAIN = "production"


@dataclass(frozen=True)
class _Source:
    text: str
    origin: str
    origin_detail: dict[str, Any] | None
    draft_extras: dict[str, Any]


async def parse(session: AsyncSession, caller: Caller, body: TeachRequest) -> TeachResult:
    view = await load_view(session, caller.tenant_id)
    company = view.companies.get(body.company_id)
    if company is None or not can_read(caller.grants, company.id):
        raise not_found("company")
    if not can_propose_anywhere(caller.grants, caller.everyone_teaches):
        raise forbidden("your roles do not allow proposing")
    source = await _source(session, caller, view, body)
    return _parse(view, company.id, source)


async def _source(
    session: AsyncSession, caller: Caller, view: OntologyView, body: TeachRequest
) -> _Source:
    """The sentence and its provenance; applies the channel gates and the charges."""
    if body.import_ref is not None:
        ensure_import_allowed(view.settings)
        return await _cited_sentence(session, caller, body.import_ref)
    ensure_live_teaching_allowed(view.settings)
    origin = body.origin or "text"
    if origin == "speech":
        ensure_speech_allowed(view.settings)
    charge(Budget.PARSE, caller.tenant_id, caller.actor_kind.value, caller.user_id)
    assert body.text is not None
    return _Source(body.text, origin, None, {"origin": origin})


async def _cited_sentence(session: AsyncSession, caller: Caller, ref: ImportRef) -> _Source:
    """A stored sentence: its parse is counted, and paid for when the import was made."""
    row = await import_service.owned_import(session, caller, ref.import_id)
    sentence = await import_service.claim_parse(session, caller, row, ref.sentence_index)
    return _Source(
        sentence.text,
        "document",
        import_service.origin_detail(row, ref.sentence_index, sentence),
        {"importRef": ref.model_dump(mode="json", by_alias=True)},
    )


def _parse(view: OntologyView, company_id: uuid.UUID, source: _Source) -> TeachResult:
    root = view.root_of(company_id)
    mine = sorted(
        (c for c in view.live_concepts() if c.company_id == company_id),
        key=lambda c: (c.born_at, str(c.id)),
    )
    if root is None:
        return _not_understood(None, [], source)
    company = str(company_id)
    root_id = str(root.id)

    def by_label(label: str) -> Concept | None:
        wanted = label.lower()
        return next((n for n in mine if n.label.lower() == wanted), None)

    def resolve(np: str) -> Concept | None:
        if not np:
            return None
        lower = np.lower()
        return by_label(title(np)) or next(
            (
                n
                for n in mine
                if n.label.lower() == singular(lower) or singular(n.label.lower()) == lower
            ),
            None,
        )

    dom_key, text = domain_prefix(source.text.strip())

    def key(fallback: str | None) -> str:
        return dom_key or fallback or DEFAULT_DOMAIN

    def key_of(n: Concept) -> str | None:
        return view.domain_key(n)

    def sid(n: Concept | None) -> str | None:
        return str(n.id) if n else None

    intents: list[Intent] = []
    drafts: list[dict[str, Any]] = []
    made: list[str] = []

    def draft(**fields: Any) -> None:
        drafts.append({**source.draft_extras, **fields})

    for it in understand(text):
        if it.kind == "spec":
            parent, child = resolve(it.obj), resolve(it.subj)
            intents.append(
                Intent(
                    kind="spec",
                    subject=it.subj,
                    object=it.obj,
                    rule=it.rule,
                    subject_resolved=child.id if child else None,
                    object_resolved=parent.id if parent else None,
                )
            )
            if parent and not child:
                plus = ", plus the rule you gave" if it.rule else ""
                draft(
                    type="spec",
                    companyId=company,
                    parentId=sid(parent),
                    label=title(it.subj),
                    rule=it.rule or "",
                    domainKey=key(key_of(parent)),
                    caption=(
                        f"{parent.label} divides: {title(it.subj)} inherits everything "
                        f"{parent.label} is{plus}."
                    ),
                )
                made.append(f"{title(it.subj)} is a {parent.label}")
            elif parent and child:
                draft(
                    type="relation",
                    aId=sid(child),
                    bId=sid(parent),
                    action="is a",
                    caption=(
                        f"{child.label} is a {parent.label}: it inherits everything "
                        f"{parent.label} is."
                    ),
                )
                made.append(f"{child.label} is a {parent.label}")
            elif child:
                draft(
                    type="concept",
                    companyId=company,
                    parentId=sid(child),
                    label=title(it.obj),
                    domainKey=key(key_of(child)),
                    action="is a kind of",
                    reverse=True,
                )
                made.append(f"{child.label} is a kind of {title(it.obj)} (new)")
            else:
                draft(
                    type="concept",
                    companyId=company,
                    parentId=root_id,
                    label=title(it.obj),
                    domainKey=key(None),
                    action="has",
                )
                draft(
                    type="spec",
                    companyId=company,
                    parentLabel=title(it.obj),
                    label=title(it.subj),
                    rule=it.rule or "",
                    domainKey=key(None),
                )
                made.append(f"{title(it.subj)} is a {title(it.obj)} (both new)")
            continue
        a, b = resolve(it.subj), resolve(it.obj)
        pred = it.pred or "relates to"
        intents.append(
            Intent(
                kind="rel",
                subject=it.subj,
                predicate=pred,
                object=it.obj,
                subject_resolved=a.id if a else None,
                object_resolved=b.id if b else None,
            )
        )
        if a and b:
            if a.id == b.id:
                continue
            draft(
                type="relation",
                aId=sid(a),
                bId=sid(b),
                action=pred,
                caption=(
                    f"{a.label} {pred} {b.label}: from {a.label} to {b.label}, "
                    "the action on the line."
                ),
            )
            made.append(f"{a.label} {pred} {b.label}")
        elif a:
            draft(
                type="concept",
                companyId=company,
                parentId=sid(a),
                label=title(it.obj),
                domainKey=key(key_of(a)),
                action=pred,
                caption=f"{title(it.obj)} is kept. {a.label} {pred} {title(it.obj)}.",
            )
            made.append(f"{a.label} {pred} {title(it.obj)} (new)")
        elif b:
            draft(
                type="concept",
                companyId=company,
                parentId=sid(b),
                label=title(it.subj),
                domainKey=key(key_of(b)),
                action=pred,
                reverse=True,
                caption=f"{title(it.subj)} is kept. {title(it.subj)} {pred} {b.label}.",
            )
            made.append(f"{title(it.subj)} (new) {pred} {b.label}")
        else:
            draft(
                type="concept",
                companyId=company,
                parentId=root_id,
                label=title(it.subj),
                domainKey=key(None),
                action="has",
            )
            draft(
                type="concept",
                companyId=company,
                parentLabel=title(it.subj),
                label=title(it.obj),
                domainKey=key(None),
                action=pred,
            )
            made.append(f"{title(it.subj)} {pred} {title(it.obj)} (both new)")

    if made:
        return _result(
            "understood",
            dom_key,
            intents,
            drafts,
            made,
            " · ".join(made) + ". Waiting for your approval on the right.",
            source,
        )

    # Nothing parsed: propose the unknown words mentioned next to a concept the sentence names.
    words = content_words(text)
    named = [n for n in mine if n.label.lower() in words]
    host = named[0] if named else root
    fresh = [w for w in dict.fromkeys(words) if not by_label(title(w))][:3]
    if not fresh or not named:
        return _not_understood(dom_key, intents, source)
    for w in fresh:
        draft(
            type="concept",
            companyId=company,
            parentId=str(host.id),
            label=title(w),
            domainKey=key(key_of(host)),
            action="relates to",
            caption=f"{title(w)} is kept.",
        )
    names = ", ".join(title(w) for w in fresh)
    return _result(
        "partly_understood",
        dom_key,
        intents,
        drafts,
        [],
        f"No action found; {names} proposed from {host.label} with “relates to”. "
        "Click the line to give it the right action.",
        source,
    )


def _not_understood(dom_key: str | None, intents: list[Intent], source: _Source) -> TeachResult:
    return _result("not_understood", dom_key, intents, [], [], NOT_UNDERSTOOD, source)


def _result(
    outcome: str,
    dom_key: str | None,
    intents: list[Intent],
    drafts: list[dict[str, Any]],
    statements: list[str],
    caption: str,
    source: _Source,
) -> TeachResult:
    return TeachResult(
        outcome=outcome,
        domain_key=dom_key,
        intents=intents,
        drafts=drafts,
        statements=statements,
        caption=caption,
        origin=source.origin,
        origin_detail=source.origin_detail,
    )
