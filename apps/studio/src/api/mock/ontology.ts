/**
 * Ontology import of the in-browser mock, mirroring `POST /ontology-imports` for the formats a
 * browser reads without a library: CSV hierarchies (`label` and `parent` columns, or `Level 1`,
 * `Level 2` and so on), OBO, RDF/XML and JSON-LD with an inline context. Turtle, N-Triples,
 * OWL/XML and XLSX are mapped by the API only; the mock refuses them with `415`. The mapping
 * follows the API's: labels by language, existing concepts reused, duplicates and cycles
 * skipped, specialisation for `subClassOf` and `is_a`, `includes` for `broader` and rows, and
 * drafts parents first. XML with a DTD and remote JSON-LD contexts are refused.
 */
import { singular, title } from '../../nl/parser';
import type * as T from '../types';
import { checkedFileName, ExtractRefusal } from './extract';

const MAX_BYTES = 20 * 1024 * 1024;
const MAX_NODES = 5000;
const RDF = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#';
const RDFS = 'http://www.w3.org/2000/01/rdf-schema#';
const OWL = 'http://www.w3.org/2002/07/owl#';
const SKOS = 'http://www.w3.org/2004/02/skos/core#';
const FORBIDDEN = new Set(['is a', 'equivalent to']);
const EXTENSION_OF_FORMAT: Record<T.OntologyFormat, string> = {
  rdf_xml: 'rdf',
  turtle: 'ttl',
  owl_xml: 'owx',
  json_ld: 'jsonld',
  n_triples: 'nt',
  obo: 'obo',
  csv: 'csv',
  xlsx: 'xlsx',
};
const REFUSED = /[<>\u0000-\u001f\u007f-\u009f\u00ad\u061c\u200b-\u200f\u2028-\u202e\u2060-\u206f\ufeff]/;

type Kind = 'spec' | 'includes';

interface Item {
  source: string;
  labels: { text: string; lang: string | null }[];
  local: string;
  parents: [string, Kind][];
  action?: string;
}

interface Parsed {
  format: T.OntologyFormat;
  items: Item[];
  relations: [string, string, string][];
  skipped: { source: string; reason: T.OntologySkipReason }[];
  table: boolean;
}

export interface ExistingConcept {
  id: string;
  label: string;
  parentId: string | null;
  domainKey: string | null;
}

export interface OntologyTarget {
  companyId: string;
  parentId: string;
  parentDomainKey: string | null;
  domainKeys: Set<string>;
  domainKey: string | null;
  languages: string[];
}

export interface MappedOntology {
  fileName: string;
  format: T.OntologyFormat;
  drafts: T.ProposalDraft[];
  notes: T.OntologyImportNote[];
  skipped: T.OntologyImportResult['skipped'];
}

/** `format` is the format to read the file as, in place of its extension. */
export function mapOntologyFile(
  rawName: string,
  bytes: Uint8Array,
  target: OntologyTarget,
  existing: ExistingConcept[],
  format?: T.OntologyFormat,
): MappedOntology {
  const fileName = checkedFileName(rawName);
  if (bytes.length > MAX_BYTES) throw new ExtractRefusal(413, 'payload_too_large', 'the file is larger than 20 MiB');
  const ext = format ? EXTENSION_OF_FORMAT[format] : fileName.includes('.') ? fileName.split('.').pop()!.toLowerCase() : '';
  const text = new TextDecoder('utf-8').decode(bytes);
  const parsed = parse(ext, text);
  return { fileName, format: parsed.format, ...mapParsed(parsed, target, existing) };
}

function parse(ext: string, text: string): Parsed {
  if (ext === 'csv') return parseCsv(text);
  if (ext === 'obo') return parseObo(text);
  if (ext === 'rdf' || ext === 'owl' || ext === 'xml') return parseRdfXml(text);
  if (ext === 'jsonld' || ext === 'json') return parseJsonLd(text);
  if (['ttl', 'nt', 'owx', 'xlsx'].includes(ext))
    throw new ExtractRefusal(415, 'unsupported_media_type', 'the in-browser mock reads CSV, OBO, RDF/XML and JSON-LD only');
  throw new ExtractRefusal(415, 'unsupported_media_type', 'OWL, SKOS, OBO, CSV and Excel hierarchies are supported');
}

function localName(iri: string): string {
  const tail = iri.split(/[#/:]/).filter(Boolean).pop() || iri;
  return decodeURIComponent(tail)
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_\s]+/g, ' ')
    .trim();
}

function parseCsv(text: string): Parsed {
  const rows = text.split(/\r?\n/).map((r) => r.split(/[,;\t]/).map((c) => c.trim()));
  const headerAt = rows.findIndex((r) => r.some(Boolean));
  if (headerAt < 0) throw new ExtractRefusal(422, 'validation_failed', 'the hierarchy has no header row');
  const header = rows[headerAt].map((h) => h.toLowerCase());
  const out: Parsed = { format: 'csv', items: [], relations: [], skipped: [], table: true };
  const col = (name: string) => header.indexOf(name);
  if (col('label') >= 0 && col('parent') >= 0) {
    const byKey = new Map<string, string>();
    const pending: [Item, string][] = [];
    rows.forEach((r, i) => {
      const label = r[col('label')];
      if (i <= headerAt || !label) return;
      const source = `row ${i + 1}`;
      const item: Item = { source, labels: [{ text: label, lang: null }], local: label, parents: [] };
      if (col('action') >= 0 && r[col('action')]) item.action = r[col('action')];
      if (col('id') >= 0 && r[col('id')] && !byKey.has('#' + r[col('id')])) byKey.set('#' + r[col('id')], source);
      if (!byKey.has(label.toLowerCase())) byKey.set(label.toLowerCase(), source);
      pending.push([item, r[col('parent')] || '']);
    });
    const unknown = new Set<string>();
    const parentOf = new Map<string, string | null>();
    for (const [item, parent] of pending) {
      const found = parent ? byKey.get('#' + parent) || byKey.get(parent.toLowerCase()) || null : null;
      if (parent && (!found || found === item.source)) unknown.add(item.source);
      parentOf.set(item.source, found);
    }
    for (let changed = true; changed; ) {
      changed = false;
      for (const [source, found] of parentOf)
        if (!unknown.has(source) && found && unknown.has(found)) {
          unknown.add(source);
          changed = true;
        }
    }
    for (const [item] of pending) {
      if (unknown.has(item.source)) {
        out.skipped.push({ source: item.source, reason: 'unknown_parent' });
        continue;
      }
      const found = parentOf.get(item.source);
      if (found) item.parents.push([found, 'includes']);
      out.items.push(item);
    }
    return out;
  }
  const levels = header
    .map((h, i) => [/^level\s*(\d+)$/.exec(h), i] as const)
    .filter(([m]) => m)
    .sort((a, b) => Number(a[0]![1]) - Number(b[0]![1]))
    .map(([, i]) => i);
  if (!levels.length)
    throw new ExtractRefusal(422, 'validation_failed', 'the hierarchy needs label and parent columns, or Level 1, Level 2 and so on');
  const byPath = new Map<string, string>();
  const carried: (string | null)[] = levels.map(() => null);
  rows.forEach((r, i) => {
    if (i <= headerAt) return;
    let fresh = 0;
    levels.forEach((c, depth) => {
      const label = r[c];
      if (!label) return;
      const parentPath = depth > 0 ? carried[depth - 1] : '';
      if (parentPath === null) {
        out.skipped.push({ source: `row ${i + 1}`, reason: 'unknown_parent' });
        return;
      }
      const path = `${parentPath}/${label.toLowerCase()}`;
      carried[depth] = path;
      for (let d = depth + 1; d < carried.length; d++) carried[d] = null;
      if (byPath.has(path)) return;
      fresh++;
      const source = fresh === 1 ? `row ${i + 1}` : `row ${i + 1} level ${depth + 1}`;
      const item: Item = { source, labels: [{ text: label, lang: null }], local: label, parents: [] };
      if (parentPath) item.parents.push([byPath.get(parentPath)!, 'includes']);
      byPath.set(path, source);
      out.items.push(item);
    });
  });
  return out;
}

function parseObo(text: string): Parsed {
  const out: Parsed = { format: 'obo', items: [], relations: [], skipped: [], table: false };
  const lines = text.split(/\r?\n/).map((l) => l.trim());
  if (!lines.slice(0, 50).some((l) => l.startsWith('format-version:')) || !lines.includes('[Term]'))
    throw new ExtractRefusal(415, 'unsupported_media_type', 'the file has no OBO header and terms');
  let stanza = 'header';
  let current: Item | null = null;
  const names = new Map<string, string>();
  let typedef: string | null = null;
  const value = (v: string) => v.replace(/\s*(\{[^}]*\})?\s*(!.*)?$/, '').trim();
  for (const line of lines) {
    const head = /^\[(\w+)\]$/.exec(line);
    if (head) {
      stanza = head[1];
      current = null;
      typedef = null;
      continue;
    }
    const tag = /^([A-Za-z_-]+):\s?(.*)$/.exec(line);
    if (!tag) continue;
    const [, name, raw] = tag;
    const v = value(raw);
    if (stanza === 'header' && name === 'import') out.skipped.push({ source: v, reason: 'remote_import_not_fetched' });
    if (stanza === 'Typedef') {
      if (name === 'id') typedef = v;
      if (name === 'name' && typedef) names.set(typedef, v);
    }
    if (stanza !== 'Term') continue;
    if (name === 'id') {
      current = { source: v, labels: [], local: v, parents: [] };
      out.items.push(current);
    } else if (current && name === 'name') current.labels.push({ text: v, lang: null });
    else if (current && name === 'is_a') current.parents.push([v.split(/\s+/)[0], 'spec']);
    else if (current && name === 'relationship') {
      const [p, d] = v.split(/\s+/);
      if (p && d) out.relations.push([current.source, p, d]);
    } else if (current && name === 'equivalent_to') out.skipped.push({ source: current.source, reason: 'equivalence_not_imported' });
  }
  out.relations = out.relations.map(([a, p, b]) => [a, names.get(p) || p, b]);
  out.items.sort((a, b) => (a.source < b.source ? -1 : a.source > b.source ? 1 : 0));
  return out;
}

function parseRdfXml(text: string): Parsed {
  if (/<!DOCTYPE/i.test(text)) throw new ExtractRefusal(415, 'unsupported_media_type', 'XML with a DTD or entities is not read');
  const doc = new DOMParser().parseFromString(text, 'application/xml');
  if (doc.getElementsByTagName('parsererror').length || doc.documentElement.namespaceURI !== RDF || doc.documentElement.localName !== 'RDF')
    throw new ExtractRefusal(415, 'unsupported_media_type', 'the XML is not RDF/XML');
  const out: Parsed = { format: 'rdf_xml', items: [], relations: [], skipped: [], table: false };
  const items = new Map<string, Item>();
  const props: { iri: string; label: string | null; domains: string[]; ranges: string[] }[] = [];
  const about = (e: Element) => e.getAttributeNS(RDF, 'about') || e.getAttributeNS(RDF, 'resource') || '';
  for (const e of Array.from(doc.documentElement.children)) {
    const iri = about(e);
    const children = Array.from(e.children);
    const is = (ns: string, name: string) => e.namespaceURI === ns && e.localName === name;
    if (is(OWL, 'Ontology')) {
      for (const c of children) if (c.namespaceURI === OWL && c.localName === 'imports') out.skipped.push({ source: about(c), reason: 'remote_import_not_fetched' });
      continue;
    }
    if (is(OWL, 'ObjectProperty')) {
      const label = children.find((c) => c.namespaceURI === RDFS && c.localName === 'label')?.textContent || null;
      const ref = (n: string) => children.filter((c) => c.namespaceURI === RDFS && c.localName === n).map(about).filter(Boolean);
      props.push({ iri, label, domains: ref('domain'), ranges: ref('range') });
      continue;
    }
    if (is(OWL, 'DatatypeProperty')) {
      out.skipped.push({ source: iri, reason: 'datatype_property' });
      continue;
    }
    if (!iri || !(is(OWL, 'Class') || is(RDFS, 'Class') || is(SKOS, 'Concept') || is(RDF, 'Description'))) continue;
    const item = items.get(iri) || { source: iri, labels: [], local: localName(iri), parents: [] };
    items.set(iri, item);
    for (const c of children) {
      const lang = c.getAttributeNS('http://www.w3.org/XML/1998/namespace', 'lang');
      if ((c.namespaceURI === RDFS && c.localName === 'label') || (c.namespaceURI === SKOS && c.localName === 'prefLabel'))
        item.labels.push({ text: c.textContent || '', lang: lang ? lang.toLowerCase() : null });
      else if (c.namespaceURI === RDFS && c.localName === 'subClassOf' && about(c)) item.parents.push([about(c), 'spec']);
      else if (c.namespaceURI === RDFS && c.localName === 'subClassOf') out.skipped.push({ source: iri, reason: 'unsupported_axiom' });
      else if (c.namespaceURI === SKOS && c.localName === 'broader' && about(c)) item.parents.push([about(c), 'includes']);
      else if (c.namespaceURI === OWL && c.localName === 'equivalentClass') out.skipped.push({ source: iri, reason: 'equivalence_not_imported' });
    }
  }
  out.items = [...items.values()].sort((a, b) => (a.source < b.source ? -1 : 1));
  for (const p of props.sort((a, b) => (a.iri < b.iri ? -1 : 1)))
    for (const d of p.domains) for (const r of p.ranges) out.relations.push([d, p.label || localName(p.iri), r]);
  return out;
}

function parseJsonLd(text: string): Parsed {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    throw new ExtractRefusal(415, 'unsupported_media_type', 'the file is not JSON');
  }
  const nodes: Record<string, unknown>[] = [];
  const walk = (v: unknown) => {
    if (Array.isArray(v)) v.forEach(walk);
    else if (v && typeof v === 'object') {
      const o = v as Record<string, unknown>;
      const ctx = o['@context'];
      if (ctx !== undefined && (typeof ctx === 'string' || (Array.isArray(ctx) && ctx.some((c) => typeof c === 'string'))))
        throw new ExtractRefusal(422, 'validation_failed', 'a remote JSON-LD @context is never fetched');
      if (o['@id']) nodes.push(o);
      Object.entries(o).forEach(([k, c]) => k !== '@context' && walk(c));
    }
  };
  walk(value);
  const out: Parsed = { format: 'json_ld', items: [], relations: [], skipped: [], table: false };
  const items = new Map<string, Item>();
  const list = (v: unknown) => (Array.isArray(v) ? v : v === undefined ? [] : [v]);
  const key = (o: Record<string, unknown>, name: string) => o[`skos:${name}`] ?? o[SKOS + name] ?? o[`rdfs:${name}`] ?? o[RDFS + name];
  for (const n of nodes) {
    const iri = String(n['@id']);
    const item = items.get(iri) || { source: iri, labels: [], local: localName(iri), parents: [] };
    items.set(iri, item);
    for (const l of [...list(key(n, 'prefLabel')), ...list(key(n, 'label')), ...list(key(n, 'altLabel'))]) {
      const lit = l as { '@value'?: string; '@language'?: string } | string;
      if (typeof lit === 'string') item.labels.push({ text: lit, lang: null });
      else if (lit['@value']) item.labels.push({ text: lit['@value'], lang: lit['@language']?.toLowerCase() || null });
    }
    for (const b of list(key(n, 'broader'))) item.parents.push([String((b as { '@id': string })['@id']), 'includes']);
    for (const b of list(key(n, 'subClassOf'))) item.parents.push([String((b as { '@id': string })['@id']), 'spec']);
    for (const c of list(key(n, 'narrower'))) {
      const child = String((c as { '@id': string })['@id']);
      const target = items.get(child) || { source: child, labels: [], local: localName(child), parents: [] };
      target.parents.push([iri, 'includes']);
      items.set(child, target);
    }
    if (key(n, 'exactMatch') || n['owl:equivalentClass']) out.skipped.push({ source: iri, reason: 'equivalence_not_imported' });
  }
  out.items = [...items.values()].sort((a, b) => (a.source < b.source ? -1 : 1));
  return out;
}

function pickLabel(item: Item, languages: string[]): { label: string; lang: string | null } {
  const cands = item.labels.filter((l) => l.text.trim());
  for (const tag of languages) {
    const t = tag.toLowerCase();
    const hit = cands.find((c) => c.lang === t) || cands.find((c) => c.lang && c.lang.split('-')[0] === t.split('-')[0]);
    if (hit) return { label: hit.text, lang: hit.lang };
  }
  const plain = cands.find((c) => c.lang === null) || cands[0];
  return plain ? { label: plain.text, lang: plain.lang } : { label: item.local, lang: null };
}

function mapParsed(parsed: Parsed, target: OntologyTarget, existing: ExistingConcept[]) {
  const drafts: T.ProposalDraft[] = [];
  const notes: T.OntologyImportNote[] = [];
  const skipped: T.OntologyImportResult['skipped'] = [...parsed.skipped];
  const nodes = new Map<string, { item: Item; label: string; lang: string | null; parent: string | null; kind: Kind; extra: [string, Kind][] }>();
  const alias = new Map<string, string>();
  const byLabel = new Map<string, string>();
  for (const item of parsed.items) {
    const picked = pickLabel(item, target.languages);
    const label = title(picked.label.normalize('NFKC').trim());
    if (!label || label.length > 120 || REFUSED.test(label)) {
      skipped.push({ source: item.source, reason: 'invalid_label' });
      continue;
    }
    const k = label.toLowerCase();
    if (byLabel.has(k)) {
      alias.set(item.source, byLabel.get(k)!);
      skipped.push({ source: item.source, label, reason: 'duplicate_label' });
      continue;
    }
    byLabel.set(k, item.source);
    nodes.set(item.source, { item, label, lang: picked.lang, parent: null, kind: 'includes', extra: [] });
  }
  for (const n of nodes.values()) {
    const named = n.item.parents
      .map(([p, k]) => [alias.get(p) || p, k] as [string, Kind])
      .filter(([p]) => nodes.has(p) && p !== n.item.source)
      .sort((a, b) => nodes.get(a[0])!.label.toLowerCase().localeCompare(nodes.get(b[0])!.label.toLowerCase()));
    if (named.length) [n.parent, n.kind] = named[0];
    n.extra = named.slice(1);
  }
  for (const source of nodes.keys()) {
    const seen = new Set<string>();
    for (let cur: string | null = source; cur; cur = nodes.get(cur)!.parent) {
      if (seen.has(cur)) {
        nodes.get(cur)!.parent = null;
        skipped.push({ source: cur, label: nodes.get(cur)!.label, reason: 'cycle' });
        break;
      }
      seen.add(cur);
    }
  }
  const resolve = (label: string) => {
    const l = label.toLowerCase();
    return existing.find((c) => c.label.toLowerCase() === l) || existing.find((c) => c.label.toLowerCase() === singular(l) || singular(c.label.toLowerCase()) === l) || null;
  };
  const state = new Map<string, { index: number | null; existing: ExistingConcept | null; domain: string; depth: number }>();
  const emit = (source: string) => {
    const chain: string[] = [];
    for (let cur: string | null = source; cur && !state.has(cur); cur = nodes.get(cur)!.parent) chain.push(cur);
    for (const s of chain.reverse()) {
      const n = nodes.get(s)!;
      const parent = n.parent ? state.get(n.parent)! : null;
      const depth = parent ? parent.depth + 1 : 1;
      const found = resolve(n.label);
      if (found) {
        const expected = parent ? parent.existing?.id ?? null : target.parentId;
        skipped.push({ source: s, label: n.label, reason: expected && found.parentId === expected ? 'already_known' : 'reused_existing' });
        state.set(s, { index: null, existing: found, domain: found.domainKey || 'production', depth });
        continue;
      }
      const inherited = parent ? parent.domain : target.parentDomainKey;
      const domain = target.domainKey || (inherited && target.domainKeys.has(inherited) ? inherited : 'production');
      const place = !parent
        ? { parentId: target.parentId }
        : parent.existing
          ? { parentId: parent.existing.id }
          : { parentLabel: nodes.get(n.parent!)!.label };
      let action = 'includes';
      if (n.item.action) {
        const a = n.item.action.normalize('NFKC').replace(/\s+/g, ' ').trim().toLowerCase().slice(0, 60);
        if (FORBIDDEN.has(a)) skipped.push({ source: s, label: n.label, reason: 'forbidden_action' });
        else if (a) action = a;
      }
      // A draft names its parent by id or by label, never both; the wire shape allows either.
      const draft = (
        n.kind === 'spec' && parent
          ? { type: 'spec', companyId: target.companyId, label: n.label, domainKey: domain, ...place }
          : { type: 'concept', companyId: target.companyId, label: n.label, domainKey: domain, action, ...place }
      ) as unknown as T.ProposalDraft;
      state.set(s, { index: drafts.length, existing: null, domain, depth });
      notes.push({ source: s, labelLanguage: n.lang, depth, requires: parent && parent.index !== null ? [parent.index] : [] });
      drafts.push(draft);
    }
  };
  for (const source of nodes.keys()) emit(source);
  const seen = new Set<string>();
  const relation = (aSource: string, bSource: string, action: string, source: string) => {
    const a = alias.get(aSource) || aSource,
      b = alias.get(bSource) || bSource;
    const sa = state.get(a),
      sb = state.get(b);
    if (!sa || !sb) return void skipped.push({ source, reason: 'unknown_parent' });
    if (a === b) return void skipped.push({ source, reason: 'unsupported_axiom' });
    const verb = action.replace(/([a-z0-9])([A-Z])/g, '$1 $2').replace(/[_\s]+/g, ' ').trim().toLowerCase().slice(0, 60);
    if (FORBIDDEN.has(verb) && action !== 'is a') return void skipped.push({ source, reason: 'forbidden_action' });
    if (seen.has(`${a}|${b}|${verb}`)) return;
    seen.add(`${a}|${b}|${verb}`);
    const end = (s: typeof sa, src: string, side: 'a' | 'b') => (s.existing ? { [`${side}Id`]: s.existing.id } : { [`${side}Label`]: nodes.get(src)!.label });
    drafts.push({ type: 'relation', companyId: target.companyId, action: verb, ...end(sa, a, 'a'), ...end(sb, b, 'b') } as unknown as T.ProposalDraft);
    notes.push({ source, labelLanguage: null, depth: null, requires: [sa.index, sb.index].filter((x): x is number => x !== null) });
  };
  for (const n of nodes.values())
    for (const [p, k] of n.extra) {
      if (k === 'spec') relation(n.item.source, p, 'is a', n.item.source);
      else relation(p, n.item.source, 'includes', n.item.source);
    }
  for (const [a, verb, b] of parsed.relations) relation(a, b, verb, a);
  if (drafts.length > MAX_NODES) throw new ExtractRefusal(413, 'payload_too_large', `the file maps to more than ${MAX_NODES} proposals`);
  return { drafts, notes, skipped };
}
