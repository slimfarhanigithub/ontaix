"""Branches of open proposals: what `Approve branch` approves and what `openBelow` counts.

A branch hangs from a `concept` or `spec` proposal's concept. It holds the open `concept` and
`spec` proposals whose `deps` or `waitFor` name a concept of the branch, transitively (each one
adds its own pending concept, and an approved concept below one of the branch stays in it, so a
branch approved in several batches stays whole), and the open `relation` proposals whose ends
are all concepts of the branch or approved concepts, at least one of them in the branch.
Dependencies resolve by id
within the root's company only: a label is looked up among that company's live concepts,
pending ones included, and a proposal of another company never enters. `change`, `source`,
`bind` and `attr` proposals are never part of a branch.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict, deque

from app.models.api.proposal import Proposal as ProposalDto
from app.models.storage.base import ProposalState, ProposalType
from app.models.storage.proposal import Proposal
from app.services.ontology_view_service import PREDICATES, OntologyView

logger = logging.getLogger(__name__)

ROOT_TYPES = frozenset({ProposalType.CONCEPT, ProposalType.SPEC})
OPEN_STATES = frozenset({ProposalState.PENDING, ProposalState.HALF_APPROVED})


class BranchIndex:
    """The dependency links of one tenant's open proposals, built once per read."""

    def __init__(self, view: OntologyView, open_proposals: list[Proposal]) -> None:
        self._view = view
        # (company, concept) -> open concept and spec proposals that depend on that concept.
        self._dependants: dict[tuple[uuid.UUID, uuid.UUID], list[Proposal]] = defaultdict(list)
        # (company, concept) -> open relation proposals with that concept at one end.
        self._relations: dict[tuple[uuid.UUID, uuid.UUID], list[Proposal]] = defaultdict(list)
        for p in open_proposals:
            if p.company_id is None:
                continue
            if p.type in ROOT_TYPES and p.concept_id is not None:
                for concept_id in self._dependencies(p):
                    self._dependants[(p.company_id, concept_id)].append(p)
            elif p.type is ProposalType.RELATION and p.relation_id is not None:
                relation = view.relations.get(p.relation_id)
                if relation is None:
                    continue
                for end in {relation.a_id, relation.b_id}:
                    self._relations[(p.company_id, end)].append(p)

    def branch(self, root: Proposal) -> list[Proposal]:
        """The open proposals of the branch rooted at `root`, `root` excluded, parents before
        children and relations last. Empty for a root that is not a concept or spec proposal."""
        company_id = root.company_id
        if root.type not in ROOT_TYPES or root.concept_id is None or company_id is None:
            return []
        concepts = {root.concept_id}
        members: list[Proposal] = []
        seen = {root.id}
        queue = deque([root.concept_id])
        while queue:
            concept_id = queue.popleft()
            for p in self._dependants.get((company_id, concept_id), []):
                if p.id in seen:
                    continue
                seen.add(p.id)
                members.append(p)
                assert p.concept_id is not None
                if p.concept_id not in concepts:
                    concepts.add(p.concept_id)
                    queue.append(p.concept_id)
            # A concept of the branch approved by an earlier batch keeps the branch connected.
            for child in self._view.children_of(concept_id):
                if not child.pending and child.id not in concepts:
                    concepts.add(child.id)
                    queue.append(child.id)
        for concept_id in list(concepts):
            for p in self._relations.get((company_id, concept_id), []):
                if p.id not in seen and self._relation_in(p, company_id, concepts):
                    seen.add(p.id)
                    members.append(p)
        return members

    def open_below(self, root: Proposal) -> int:
        return len(self.branch(root))

    def _dependencies(self, proposal: Proposal) -> set[uuid.UUID]:
        """The concepts of the proposal's company its `deps` and `waitFor` name."""
        assert proposal.company_id is not None
        labels = [str(d) for d in proposal.deps if str(d) not in PREDICATES]
        if proposal.wait_for:
            labels.append(proposal.wait_for)
        found: set[uuid.UUID] = set()
        for label in labels:
            concept = self._view.find_label(proposal.company_id, label)
            if concept is not None and concept.id != proposal.concept_id:
                found.add(concept.id)
        return found

    def _relation_in(
        self, proposal: Proposal, company_id: uuid.UUID, concepts: set[uuid.UUID]
    ) -> bool:
        relation = self._view.relations.get(proposal.relation_id or uuid.UUID(int=0))
        if relation is None:
            return False
        for end_id in (relation.a_id, relation.b_id):
            if end_id in concepts:
                continue
            end = self._view.concepts.get(end_id)
            if end is None or end.company_id != company_id or end.pending or end.dying_at:
                return False
        return True


def annotate(dto: ProposalDto, row: Proposal, index: BranchIndex) -> ProposalDto:
    """The DTO with `openBelow` set when `row` is an open concept or spec proposal with open
    proposals in its branch."""
    if row.type not in ROOT_TYPES or row.state not in OPEN_STATES:
        return dto
    below = index.open_below(row)
    return dto.model_copy(update={"open_below": below}) if below else dto
