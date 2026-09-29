/**
 * Live-update channel. Every state change reaches the Studio as one envelope, the shape
 * contracts/events.yaml defines for the WebSocket. The in-browser mock publishes onto this bus
 * directly; a WebSocket client publishes onto the same bus when a real API is configured.
 */
import type { Actor, Artefacts, Concept, Proposal, Relation } from './types';

export type EventType =
  | 'proposal.created'
  | 'proposal.half_approved'
  | 'proposal.approved'
  | 'proposal.rejected'
  | 'concept.born'
  | 'concept.changed'
  | 'concept.dying'
  | 'concept.conflict'
  | 'relation.created'
  | 'relation.changed'
  | 'relation.removed'
  | 'source.created'
  | 'source.changed'
  | 'source.removed'
  | 'binding.created'
  | 'binding.changed'
  | 'binding.removed'
  | 'attribute.changed'
  | 'domain_product.changed'
  | 'company.created'
  | 'company.removed'
  | 'settings.changed'
  | 'appearance.changed'
  | 'view_state.changed'
  /** Control message: the client's state is behind and must reload `GET /scene`. */
  | 'snapshot.required';

export interface Envelope<P = Record<string, unknown>> {
  id: string;
  type: EventType;
  occurredAt: string;
  tenantId: string;
  sequence: number;
  actor: Actor;
  bulk: boolean;
  payload: P;
}

export interface ProposalEventPayload {
  proposal: Proposal;
  artefacts: Artefacts;
  cascaded: Proposal[];
  caption?: string;
}

export interface ConceptConflictPayload {
  concepts: Concept[];
  relation: Relation;
  caption: string;
}

export type EventHandler = (e: Envelope) => void;

export interface EventBus {
  emit(e: Envelope): void;
  subscribe(fn: EventHandler): () => void;
}

export function createEventBus(): EventBus {
  const handlers = new Set<EventHandler>();
  return {
    emit(e) {
      for (const fn of [...handlers]) fn(e);
    },
    subscribe(fn) {
      handlers.add(fn);
      return () => {
        handlers.delete(fn);
      };
    },
  };
}

/** The bus the store listens on. */
export const liveEvents: EventBus = createEventBus();
