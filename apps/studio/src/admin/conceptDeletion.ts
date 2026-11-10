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
import { t } from '../i18n/i18n';

/** Names listed in the confirmation before the rest collapse into `and N more`. */
export const LISTED_NAMES = 6;

export interface ConceptDeletion {
  descendants: Node[];
  relations: number;
}

/** True when the drawer offers Delete, Rename and Move to domain: an approved, live concept the server knows. */
export const canDeleteFromDrawer = (n: Node): boolean => n.kind === 'concept' && !n.pending && !n.dying && !!n.sid;

/** `a, b and c`. */
const listOf = (parts: string[]) =>
  parts.length < 2 ? parts.join('') : `${parts.slice(0, -1).join(t('admin.impact.listSeparator'))}${t('admin.impact.listAnd')}${parts[parts.length - 1]}`;

/** ` and 3 more`, the names a confirmation does not list; empty when every name is listed. */
const moreText = (hidden: number): string => (hidden > 0 ? t('admin.impact.more', { n: hidden }) : '');

/**
 * The confirmation body of a company, domain or bulk deletion, from the API's deletion impact,
 * in the style of the concept deletion text: `Its 3 concepts (A, B, C), 2 descendants, 5 relations
 * (1 across companies), 1 source, 2 bindings and 4 attributes go with it. 2 open proposals are
 * rejected with them. This proposes a change for approval.` Names are the API's, at most six, then
 * `and <k> more`; sources are named for a whole company only.
 */
export function impactText(i: DeletionImpact, wholeCompany: boolean): string {
  const total = i.concepts + i.descendants;
  const named = i.names.length ? t('admin.impact.named', { names: i.names.join(t('admin.impact.listSeparator')), more: moreText(total - i.names.length) }) : '';
  const parts = [
    `${t('admin.impact.concepts', { n: i.concepts })}${named}`,
    t('admin.impact.descendants', { n: i.descendants }),
    `${t('admin.impact.relations', { n: i.relations })}${i.crossCompanyRelations ? t('admin.impact.acrossCompanies', { n: i.crossCompanyRelations }) : ''}`,
  ];
  if (wholeCompany) parts.push(t('admin.impact.sources', { n: i.sources }));
  parts.push(t('admin.impact.bindings', { n: i.bindings }), t('admin.impact.attributes', { n: i.attributes }));
  const cascade = i.cascadedProposals ? t('admin.impact.cascade', { n: i.cascadedProposals }) : '';
  return t('admin.impact.body', { list: listOf(parts), cascade });
}

export function conceptDeletion(s: SceneState, n: Node): ConceptDeletion {
  const descendants = descendantsOf(s, n);
  const doomed = new Set<Node>([n, ...descendants]);
  const relations = s.links.filter((l) => l.kind !== 'bind' && !l.dying && (doomed.has(l.a) || doomed.has(l.b))).length;
  return { descendants, relations };
}

/** The confirmation body, for example `Its 4 descendants (Offerings, Apps, Data, AI) and 5 relations go with it. …`. */
export function deletionText(names: string[], relations: number): string {
  if (!names.length) return t('admin.deletion.relationsOnly', { n: relations });
  const shown = names.slice(0, LISTED_NAMES).join(t('admin.impact.listSeparator'));
  return t('admin.deletion.withDescendants', { n: names.length, names: shown, more: moreText(names.length - LISTED_NAMES), r: relations });
}
