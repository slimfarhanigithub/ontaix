/**
 * What deleting a concept takes with it, and the confirmation text that names it. Descendants
 * are the live cells born from it, transitively through the parent chain, as the API's
 * `descendants_of` counts them; relations are every live non-binding link touching the concept
 * or a descendant, each counted once.
 */
import type { DeletionImpact } from '../api/types';
import { descendantsOf } from '../canvas/lineage';
import type { SceneState } from '../canvas/state';
import type { Node } from '../canvas/types';

/** Names listed in the confirmation before the rest collapse into `and N more`. */
export const LISTED_NAMES = 6;

export interface ConceptDeletion {
  descendants: Node[];
  relations: number;
}

/** True when the drawer offers Delete, Rename and Move to domain: an approved, live concept the server knows. */
export const canDeleteFromDrawer = (n: Node): boolean => n.kind === 'concept' && !n.pending && !n.dying && !!n.sid;

const count = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;

/** `a, b and c`. */
const listOf = (parts: string[]) => (parts.length < 2 ? parts.join('') : `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`);

/**
 * The confirmation body of a company, domain or bulk deletion, from the API's deletion impact,
 * in the style of the concept deletion text: `Its 3 concepts (A, B, C), 2 descendants, 5 relations
 * (1 across companies), 1 source, 2 bindings and 4 attributes go with it. 2 open proposals are
 * rejected with them. This proposes a change for approval.` Names are the API's, at most six, then
 * `and <k> more`; sources are named for a whole company only.
 */
export function impactText(i: DeletionImpact, wholeCompany: boolean): string {
  const total = i.concepts + i.descendants;
  const more = total > i.names.length ? ` and ${total - i.names.length} more` : '';
  const named = i.names.length ? ` (${i.names.join(', ')}${more})` : '';
  const parts = [
    `${count(i.concepts, 'concept')}${named}`,
    count(i.descendants, 'descendant'),
    `${count(i.relations, 'relation')}${i.crossCompanyRelations ? ` (${i.crossCompanyRelations} across companies)` : ''}`,
  ];
  if (wholeCompany) parts.push(count(i.sources, 'source'));
  parts.push(count(i.bindings, 'binding'), count(i.attributes, 'attribute'));
  const cascade = i.cascadedProposals ? ` ${count(i.cascadedProposals, 'open proposal')} ${i.cascadedProposals === 1 ? 'is' : 'are'} rejected with them.` : '';
  return `Its ${listOf(parts)} go with it.${cascade} This proposes a change for approval.`;
}

export function conceptDeletion(s: SceneState, n: Node): ConceptDeletion {
  const descendants = descendantsOf(s, n);
  const doomed = new Set<Node>([n, ...descendants]);
  const relations = s.links.filter((l) => l.kind !== 'bind' && !l.dying && (doomed.has(l.a) || doomed.has(l.b))).length;
  return { descendants, relations };
}

/** The confirmation body, for example `Its 4 descendants (Offerings, Apps, Data, AI) and 5 relations go with it. …`. */
export function deletionText(names: string[], relations: number): string {
  const rels = `${relations} relation${relations === 1 ? '' : 's'}`;
  const tail = 'This proposes a change for approval.';
  if (!names.length) return `Its ${rels} ${relations === 1 ? 'goes' : 'go'} with it. ${tail}`;
  const shown = names.slice(0, LISTED_NAMES).join(', ');
  const more = names.length > LISTED_NAMES ? ` and ${names.length - LISTED_NAMES} more` : '';
  const desc = `${names.length} descendant${names.length === 1 ? '' : 's'}`;
  return `Its ${desc} (${shown}${more}) and ${rels} go with it. ${tail}`;
}
