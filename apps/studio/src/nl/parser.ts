/**
 * Rule-based teach parser: subject, action, object; "A is a B"; "A that ... is a B"; lists;
 * passives; an "In <domain>, ..." prefix. Ported from reference/ontaix-studio-reference.html
 * lines 841-863 (`STOP`, `title`, `DET`, `VERBS_LEX`, `CANON`, `VERB_RE`, `singular`,
 * `cleanNP`, `splitList`, `understand`) and the domain prefix of line 865.
 */

export const STOP = new Set(
  'a an the and or of to in on at for with by from we our your their my is are was were be been it its this that these those who which what how many much some any all every each new old have has had do does did make makes use uses also very more most less than into over under about through there here when where then them they you he she his her run runs'.split(
    ' ',
  ),
);

export const title = (s: string): string => s.charAt(0).toUpperCase() + s.slice(1);

const DET = /^(?:a|an|the|each|every|all|our|its|their|some|many|any|one|this|that|these|those|of|new)\s+/;

export const VERBS_LEX = [
  'is a kind of', 'is a type of', 'is part of', 'is made of', 'is made from', 'consists of', 'is composed of', 'is executed on', 'is executed by', 'is placed by', 'is bought from', 'is sold to', 'is stored in', 'is produced by', 'is produced in', 'is checked by', 'is inspected by', 'is monitored by', 'is handled by', 'is managed by', 'is owned by', 'is defined by', 'is validated by', 'is scheduled by', 'is staffed by', 'is billed by', 'is charged to', 'is fulfilled by', 'is delivered by', 'is shipped as', 'is grouped in', 'is limited by', 'is priced from', 'is earned through', 'is governed by', 'is followed by', 'is preceded by', 'belongs to', 'reports to', 'depends on', 'delivers to', 'sells to', 'buys from', 'leads to', 'results in', 'applies to', 'refers to', 'runs in', 'runs on', 'works in', 'works on', 'operates', 'manages', 'owns', 'produces', 'makes', 'builds', 'creates', 'generates', 'uses', 'consumes', 'needs', 'requires', 'contains', 'includes', 'has', 'have', 'holds', 'runs', 'executes', 'places', 'receives', 'sends', 'ships', 'delivers', 'stores', 'tracks', 'records', 'monitors', 'measures', 'checks', 'inspects', 'validates', 'tests', 'triggers', 'starts', 'schedules', 'plans', 'assigns', 'employs', 'trains', 'certifies', 'serves', 'supplies', 'provides', 'feeds', 'defines', 'specifies', 'updates', 'evolves', 'issues', 'pays', 'invoices', 'bills', 'approves', 'raises', 'handles', 'follows', 'precedes', 'supports', 'maintains', 'repairs', 'replaces', 'installs', 'packs', 'loads', 'routes', 'processes', 'transforms', 'assembles', 'welds', 'paints', 'moves', 'carries', 'transports', 'fulfils', 'fulfills', 'covers', 'governs', 'groups', 'limits', 'prices', 'signs', 'opens', 'closes',
];

export const CANON: Record<string, string> = {};
const VARIANTS: string[] = [];
for (const v of VERBS_LEX) {
  CANON[v] = v;
  VARIANTS.push(v);
  if (/^is /.test(v)) {
    const a = v.replace(/^is /, 'are ');
    CANON[a] = v;
    VARIANTS.push(a);
  } else if (!/\s/.test(v)) {
    let b: string | null = null;
    if (v === 'has') b = 'have';
    else if (/ies$/.test(v)) b = v.replace(/ies$/, 'y');
    else if (/(ch|sh|ss|x|z)es$/.test(v)) b = v.replace(/es$/, '');
    else if (/s$/.test(v)) b = v.slice(0, -1);
    if (b && b.length > 2) {
      CANON[b] = v;
      VARIANTS.push(b);
    }
  }
}

export const VERB_RE = new RegExp(
  '\\b(' +
    VARIANTS.sort((a, b) => b.length - a.length)
      .map((v) => v.replace(/\s+/g, '\\s+'))
      .join('|') +
    ')\\b',
);

export const singular = (w: string): string =>
  w
    .replace(/ies$/, 'y')
    .replace(/(ch|sh|s|x|z)es$/, '$1')
    .replace(/([^s])s$/, '$1');

export function cleanNP(np: string): string {
  np = np
    .trim()
    .replace(/[.!?,;:]+$/, '')
    .replace(/^[,;:\s]+/, '');
  let guard = 0;
  while (DET.test(np) && guard++ < 4) np = np.replace(DET, '');
  const w = np.split(/\s+/).filter(Boolean);
  if (!w.length) return '';
  w[w.length - 1] = singular(w[w.length - 1]);
  return w.join(' ');
}

export function splitList(np: string): string[] {
  return np
    .split(/\s*,\s*|\s+and\s+|\s+or\s+/)
    .map(cleanNP)
    .filter(Boolean);
}

export interface ParsedIntent {
  kind: 'spec' | 'rel';
  subj: string;
  pred?: string;
  obj: string;
  rule?: string;
}

/** The intents of one sentence. */
export function understand(text: string): ParsedIntent[] {
  const lower = text
    .toLowerCase()
    .trim()
    .replace(/\s+/g, ' ')
    .replace(/[.!?]+$/, '');
  const out: ParsedIntent[] = [];
  let m: RegExpMatchArray | null;
  // "a machine that has run 5,000 hours is a machine due for maintenance" -> specialisation with a rule
  if ((m = lower.match(/^(.+?)\s+(?:that|who|which)\s+(.+?)\s+(?:is|are)\s+(?:a |an |the )?(.+)$/))) {
    out.push({ kind: 'spec', subj: cleanNP(m[3]), rule: m[2].trim(), obj: cleanNP(m[1]) });
    return out;
  }
  // "a scrapped product is a defective product" / "operators are employees" -> specialisation
  if (
    (m = lower.match(/^(.+?)\s+(?:is|are)\s+(?:a |an )?(?:kind of |type of |sort of )?(.+)$/)) &&
    !VERB_RE.test(m[2]) &&
    !/\s(?:by|in|on|to|of|from|with)\s/.test(m[2])
  ) {
    out.push({ kind: 'spec', subj: cleanNP(m[1]), obj: cleanNP(m[2]) });
    return out;
  }
  // clauses: "a line has machines, and every machine has sensors"
  const clauses = lower.split(
    /\s*[;]\s*|\s*,\s*(?:and\s+)?(?=(?:a|an|the|each|every|all|our|its|their)\s)|\s+and\s+(?=(?:a|an|the|each|every|all|our|its|their)\s)/,
  );
  for (const cl of clauses) {
    let v: RegExpExecArray | null = null;
    const g = new RegExp(VERB_RE.source, 'g');
    let mm: RegExpExecArray | null;
    while ((mm = g.exec(cl))) {
      if (cleanNP(cl.slice(0, mm.index))) {
        v = mm;
        break;
      }
    }
    if (!v) continue;
    const subj = cleanNP(cl.slice(0, v.index));
    const pred = CANON[v[1].replace(/\s+/g, ' ')] || v[1];
    let rest = cl.slice(v.index + v[0].length);
    if (!subj) continue;
    const pp = rest.match(/^(.*?)\s+(to|into|from|in|on|at|with|through|for)\s+(.+)$/);
    if (pp && cleanNP(pp[1])) {
      rest = pp[1];
      for (const obj of splitList(pp[3])) out.push({ kind: 'rel', subj, pred: `${pred} ${pp[2]}`, obj });
    }
    for (const obj of splitList(rest)) out.push({ kind: 'rel', subj, pred, obj });
  }
  return out;
}

export const DOMAIN_PREFIX = /^in (production|supply chain|supply|sales|logistics|quality|maintenance|finance|people|hr|engineering)[,:]?\s*/;

/** Strips an "In <domain>, " prefix; returns the domain key and the remaining text. */
export function domainPrefix(text: string): { domainKey: string | null; text: string } {
  const dm = text.toLowerCase().match(DOMAIN_PREFIX);
  if (!dm) return { domainKey: null, text };
  const k = dm[1].startsWith('supply') ? 'supply' : dm[1] === 'hr' ? 'people' : dm[1];
  return { domainKey: k, text: text.slice(dm[0].length) };
}

/** Words of a sentence that can name a concept, for the fallback. */
export function contentWords(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z\s-]/g, ' ')
    .split(/\s+/)
    .filter((w) => w.length > 3 && !STOP.has(w))
    .map(singular);
}
