/**
 * LOCAL FALLBACK for `POST /teach/parse`, used only while the real API does not serve that route.
 * It reads the sentence in the browser with the verbatim parser and resolves the concepts it
 * names against the scene the Studio already holds, producing the same `TeachResult` the mock
 * returns. Nothing is written here: the drafts still go to the API as proposals.
 */
import type { SceneState } from '../canvas/state';
import type { Node } from '../canvas/types';
import { contentWords, domainPrefix, singular, title, understand } from '../nl/parser';
import type { DomainKey, Intent, ProposalDraft, TeachResult } from './types';

const NOT_UNDERSTOOD =
  'Try “<subject> <action> <object>”, “A is a B”, or “A that … is a B”. Start with “In quality, …” to choose the domain product.';

export function localTeachParse(s: SceneState, body: { companyId: string; text: string }): TeachResult {
  const co = s.companies.find((c) => c.sid === body.companyId);
  const root = co?.root;
  if (!co || !root?.sid) return notUnderstood(null, []);
  const rootId = root.sid;
  const mine = () => s.nodes.filter((n) => n.company === co && n.kind !== 'source' && !n.dying && n.sid);
  const byLabel = (label: string) => mine().find((n) => n.label.toLowerCase() === label.toLowerCase()) || null;
  const resolve = (np: string): Node | null => {
    if (!np) return null;
    const lower = np.toLowerCase();
    return (
      byLabel(title(np)) ||
      mine().find((n) => n.label.toLowerCase() === singular(lower) || singular(n.label.toLowerCase()) === lower) ||
      null
    );
  };

  const { domainKey: domKey, text } = domainPrefix(body.text.trim());
  const key = (fallback: string | null | undefined) => (domKey || fallback || 'production') as DomainKey;
  const keyOf = (n: Node) => n.domain?.key ?? null;
  const intents: Intent[] = [];
  const drafts: ProposalDraft[] = [];
  const made: string[] = [];
  const companyId = co.sid as string;

  for (const it of understand(text)) {
    if (it.kind === 'spec') {
      const parent = resolve(it.obj),
        child = resolve(it.subj);
      intents.push({ kind: 'spec', subject: it.subj, object: it.obj, rule: it.rule, subjectResolved: child?.sid ?? null, objectResolved: parent?.sid ?? null });
      if (parent && !child) {
        drafts.push({
          type: 'spec',
          companyId,
          parentId: parent.sid as string,
          label: title(it.subj),
          rule: it.rule || '',
          domainKey: key(keyOf(parent)),
          caption: `${parent.label} divides: ${title(it.subj)} inherits everything ${parent.label} is${it.rule ? ', plus the rule you gave' : ''}.`,
        });
        made.push(`${title(it.subj)} is a ${parent.label}`);
      } else if (parent && child) {
        drafts.push({ type: 'relation', aId: child.sid as string, bId: parent.sid as string, action: 'is a', caption: `${child.label} is a ${parent.label}: it inherits everything ${parent.label} is.` });
        made.push(`${child.label} is a ${parent.label}`);
      } else if (!parent && child) {
        drafts.push({ type: 'concept', companyId, parentId: child.sid as string, label: title(it.obj), domainKey: key(keyOf(child)), action: 'is a kind of', reverse: true });
        made.push(`${child.label} is a kind of ${title(it.obj)} (new)`);
      } else {
        drafts.push({ type: 'concept', companyId, parentId: rootId, label: title(it.obj), domainKey: key(null), action: 'has' });
        drafts.push({ type: 'spec', companyId, parentId: '', parentLabel: title(it.obj), label: title(it.subj), rule: it.rule || '', domainKey: key(null) });
        made.push(`${title(it.subj)} is a ${title(it.obj)} (both new)`);
      }
      continue;
    }
    const a = resolve(it.subj),
      b = resolve(it.obj);
    const pred = it.pred || 'relates to';
    intents.push({ kind: 'rel', subject: it.subj, predicate: pred, object: it.obj, subjectResolved: a?.sid ?? null, objectResolved: b?.sid ?? null });
    if (a && b) {
      if (a === b) continue;
      drafts.push({ type: 'relation', aId: a.sid as string, bId: b.sid as string, action: pred, caption: `${a.label} ${pred} ${b.label}: from ${a.label} to ${b.label}, the action on the line.` });
      made.push(`${a.label} ${pred} ${b.label}`);
    } else if (a && !b) {
      drafts.push({ type: 'concept', companyId, parentId: a.sid as string, label: title(it.obj), domainKey: key(keyOf(a)), action: pred, caption: `${title(it.obj)} is kept. ${a.label} ${pred} ${title(it.obj)}.` });
      made.push(`${a.label} ${pred} ${title(it.obj)} (new)`);
    } else if (!a && b) {
      drafts.push({ type: 'concept', companyId, parentId: b.sid as string, label: title(it.subj), domainKey: key(keyOf(b)), action: pred, reverse: true, caption: `${title(it.subj)} is kept. ${title(it.subj)} ${pred} ${b.label}.` });
      made.push(`${title(it.subj)} (new) ${pred} ${b.label}`);
    } else {
      drafts.push({ type: 'concept', companyId, parentId: rootId, label: title(it.subj), domainKey: key(null), action: 'has' });
      drafts.push({ type: 'concept', companyId, parentId: '', parentLabel: title(it.subj), label: title(it.obj), domainKey: key(null), action: pred });
      made.push(`${title(it.subj)} ${pred} ${title(it.obj)} (both new)`);
    }
  }
  const domainKey = (domKey as DomainKey) || null;
  if (made.length)
    return { outcome: 'understood', domainKey, intents, drafts, statements: made, caption: made.join(' · ') + '. Waiting for your approval on the right.', scene: null };

  // Nothing parsed: propose the unknown words mentioned next to a concept the sentence names.
  const words = contentWords(text);
  const host = mine().find((n) => words.includes(n.label.toLowerCase())) || root;
  const fresh = [...new Set(words)].filter((w) => !byLabel(title(w))).slice(0, 3);
  if (!fresh.length || !mine().some((n) => words.includes(n.label.toLowerCase()))) return notUnderstood(domainKey, intents);
  return {
    outcome: 'partly_understood',
    domainKey,
    intents,
    drafts: fresh.map((w) => ({ type: 'concept' as const, companyId, parentId: host.sid as string, label: title(w), domainKey: key(keyOf(host)), action: 'relates to', caption: `${title(w)} is kept.` })),
    statements: [],
    caption: `No action found; ${fresh.map(title).join(', ')} proposed from ${host.label} with “relates to”. Click the line to give it the right action.`,
    scene: null,
  };
}

function notUnderstood(domainKey: DomainKey | null, intents: Intent[]): TeachResult {
  return { outcome: 'not_understood', domainKey, intents, drafts: [], statements: [], caption: NOT_UNDERSTOOD, scene: null };
}
