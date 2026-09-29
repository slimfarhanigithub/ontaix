/**
 * What deleting a concept takes with it, and the confirmation text that names it. Descendants
 * are the live cells born from it, transitively through the parent chain, as the API's
 * `descendants_of` counts them; relations are every live non-binding link touching the concept
 * or a descendant, each counted once.
 */
import { descendantsOf } from '../canvas/lineage';
import type { SceneState } from '../canvas/state';
import type { Node } from '../canvas/types';

/** Names listed in the confirmation before the rest collapse into `and N more`. */
export const LISTED_NAMES = 6;

export interface ConceptDeletion {
  descendants: Node[];
  relations: number;
}

/** True when the drawer offers Delete: an approved, live concept the server knows. */
export const canDeleteFromDrawer = (n: Node): boolean => n.kind === 'concept' && !n.pending && !n.dying && !!n.sid;

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
