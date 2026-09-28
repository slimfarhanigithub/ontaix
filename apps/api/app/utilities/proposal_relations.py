"""Which relations a proposal owns and which ones it points at.

A proposal owns the pending relations it created (`relation_id`, `relation_ids`). A change
proposal also points at a live relation through `payload.relationId` without owning it: that
relation is only a target, and rejecting the change must leave it untouched.
"""

from __future__ import annotations

import uuid

from app.models.storage.proposal import Proposal


def own_relation_ids(proposal: Proposal) -> list[uuid.UUID]:
    """The relations the proposal created itself, birth relation first."""
    ids = list(proposal.relation_ids or [])
    if proposal.relation_id:
        ids.insert(0, proposal.relation_id)
    return ids


def touched_relation_ids(proposal: Proposal) -> list[uuid.UUID]:
    """The relations the proposal owns plus the live relation a change proposal targets."""
    ids = own_relation_ids(proposal)
    target = proposal.payload.get("relationId") if proposal.payload else None
    if target:
        ids.append(uuid.UUID(str(target)))
    return ids
