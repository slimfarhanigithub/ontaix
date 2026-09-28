/**
 * The scripted story: a manufacturer describes itself. Each scene creates its proposals through
 * the API in the order and pacing of reference/ontaix-studio-reference.html lines 733-838
 * (`caption`, `scenes`, `setScene`, `playScene`, `next`, `wait`) and the proposal helpers of
 * lines 598-607, 613 and 733. Text is verbatim.
 */
import { api } from '../api/client';
import type { DomainKey, ProposalDraft } from '../api/types';
import { W_, REDUCED } from '../canvas/constants';
import { drawBirth } from '../canvas/division';
import type { Company } from '../canvas/types';
import { random } from '../runtime/rng';
import { store } from '../store/store';
import { SCENES } from './scenes';

const s = store.s;

/** Waits, or returns at once while animations are skipped. */
export const wait = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, s.SKIP ? 0 : ms));

const caption = (k: string, t: string) => store.caption(k, t);

async function post(draft: ProposalDraft): Promise<void> {
  await store.propose(draft);
}

/**
 * Draws the random numbers a draft's birth consumes, in the reference order, and puts the link
 * bend on the draft for the server to store. Concept and spec drafts draw angle noise, node
 * seed and link seed; relation drafts draw the link seed only.
 */
export function withSeed<D extends ProposalDraft>(draft: D): D {
  if (draft.type === 'concept' || draft.type === 'spec') {
    const draws = drawBirth();
    store.rememberBirth(draft.companyId, draft.label, draws);
    return { ...draft, seed: draws.link };
  }
  if (draft.type === 'relation') return { ...draft, seed: random() };
  return draft;
}

/** A concept born from `parentLabel`, in `domainKey`, joined by `pred`. */
export async function pConcept(
  parentLabel: string,
  label: string,
  domainKey: DomainKey,
  pred: string,
  cap?: string,
  company?: Company | null,
  reverse?: boolean,
): Promise<void> {
  const host = store.findNode(parentLabel, company);
  if (!host || !host.sid || !host.company?.sid) return;
  await post(
    withSeed({
      type: 'concept',
      companyId: host.company.sid,
      parentId: host.sid,
      parentLabel,
      label,
      domainKey,
      action: pred,
      reverse: !!reverse,
      caption: cap,
    }),
  );
}

/** A specialisation of `parentLabel` with a rule. */
export async function pSpec(
  parentLabel: string,
  label: string,
  rule: string,
  cap: string | undefined,
  domainKey: DomainKey,
  company?: Company | null,
): Promise<void> {
  const host = store.findNode(parentLabel, company);
  if (!host || !host.sid || !host.company?.sid) return;
  await post(withSeed({ type: 'spec', companyId: host.company.sid, parentId: host.sid, parentLabel, label, rule, domainKey, caption: cap }));
}

export async function pRelation(aLabel: string, pred: string, bLabel: string, cap?: string, company?: Company | null): Promise<void> {
  const a = store.findNode(aLabel, company),
    b = store.findNode(bLabel, company);
  if (!a || !b || !a.sid || !b.sid) return;
  await post(withSeed({ type: 'relation', aId: a.sid, bId: b.sid, aLabel, bLabel, action: pred, caption: cap }));
}

export async function pSource(company: Company, label: string, kind: string, cap?: string): Promise<void> {
  if (!company.sid) return;
  await post({ type: 'source', companyId: company.sid, label, kindText: kind, caption: cap });
}

export async function pBind(company: Company, sourceLabel: string, conceptLabels: string[], cap?: string): Promise<void> {
  const src = s.nodes.find((n) => n.kind === 'source' && n.company === company && n.label === sourceLabel);
  if (!src || !src.sid) return;
  const ids = conceptLabels
    .map((l) => store.findNode(l, company))
    .map((n) => n?.sid)
    .filter((x): x is string => !!x);
  if (!ids.length) return;
  await post({ type: 'bind', sourceId: src.sid, conceptIds: ids, caption: cap });
}

export async function pEquiv(labelA: string, companyA: Company, labelB: string, companyB: Company, cap?: string): Promise<void> {
  const a = store.findNode(labelA, companyA),
    b = store.findNode(labelB, companyB);
  if (!a || !b || !a.sid || !b.sid) return;
  await post(
    withSeed({
      type: 'relation',
      aId: a.sid,
      bId: b.sid,
      aLabel: a.label,
      bLabel: b.label,
      action: 'equivalent to',
      caption:
        cap ||
        `${a.label} at ${a.company?.name} is the same concept as ${b.label} at ${b.company?.name}. One meaning, two vocabularies, both kept.`,
    }),
  );
}

/** Adds a company to the view; its starter vocabulary arrives as proposals through events. */
export async function addCompany(name: string, sub: string, seed: boolean): Promise<Company | null> {
  const created = await api.createCompany({ name, sub, start: seed ? 'starter_vocabulary' : 'one_cell' });
  const c = store.companyBySid(created.company.id);
  if (c) {
    s.activeCompany = c;
    store.renderCompanies();
  }
  return c;
}

const runs: Record<number, () => Promise<void>> = {
  1: async () => {
    caption('Production · seven proposals', 'The first domain product. Plant operations own it, version it and publish it for everyone else.');
    await pConcept('Northwind Industries', 'Plant', 'production', 'operates', 'Plant is kept in Production.');
    await wait(W_);
    await pConcept('Plant', 'Production line', 'production', 'runs', 'Production line is kept.');
    await wait(W_);
    await pConcept('Production line', 'Machine', 'production', 'has', 'Machine is kept.');
    await wait(W_);
    await pConcept('Production line', 'Shift', 'production', 'runs in', 'Shift is kept.');
    await wait(W_);
    await pConcept('Shift', 'Operator', 'production', 'staffed by', 'Operator is kept.');
    await wait(W_);
    await pConcept('Production line', 'Work order', 'production', 'executes', 'Work order is kept.');
    await wait(W_);
    await pConcept('Work order', 'Product', 'production', 'produces', 'Product is kept. Production is now a product of its own: owned, versioned, consumable.');
  },
  2: async () => {
    caption('Supply chain · six proposals', 'A second domain product. Its first concepts hang off Product, so those relations cross the boundary between the two products.');
    await pConcept('Product', 'Bill of materials', 'supply', 'defined by', 'Bill of materials is kept in Supply chain. Product is defined by it: a relation across two domain products.');
    await wait(W_);
    await pConcept('Bill of materials', 'Material', 'supply', 'lists', 'Material is kept.');
    await wait(W_);
    await pConcept('Material', 'Supplier', 'supply', 'bought from', 'Supplier is kept.');
    await wait(W_);
    await pConcept('Supplier', 'Purchase order', 'supply', 'receives', 'Purchase order is kept.');
    await wait(W_);
    await pConcept('Material', 'Warehouse', 'supply', 'stored in', 'Warehouse is kept.');
    await wait(W_);
    await pConcept('Warehouse', 'Stock level', 'supply', 'tracks', 'Stock level is kept.');
  },
  3: async () => {
    caption('Sales · seven proposals', 'Commercial owns this product. Its orders reach into Production through relations, not copies.');
    await pConcept('Northwind Industries', 'Customer', 'sales', 'serves', 'Customer is kept in Sales.');
    await wait(W_);
    await pConcept('Customer', 'Sales region', 'sales', 'grouped in', 'Sales region is kept.');
    await wait(W_);
    await pConcept('Customer', 'Quotation', 'sales', 'requests', 'Quotation is kept.');
    await wait(W_);
    await pConcept('Quotation', 'Sales order', 'sales', 'becomes', 'Sales order is kept.');
    await wait(W_);
    await pConcept('Sales order', 'Price list', 'sales', 'priced from', 'Price list is kept.');
    await wait(W_);
    await pRelation('Sales order', 'contains', 'Product', 'Sales order contains Product: Sales reads Production’s definition of Product rather than inventing its own.');
    await wait(400);
    await pRelation('Sales order', 'triggers', 'Work order', 'Sales order triggers Work order: the hand-over between the two domain products is explicit.');
  },
  4: async () => {
    caption('Logistics · four proposals', 'Distribution owns the last mile. It consumes Sales’ orders and Supply chain’s warehouses.');
    await pConcept('Sales order', 'Delivery', 'logistics', 'fulfilled by', 'Delivery is kept in Logistics.');
    await wait(W_);
    await pConcept('Delivery', 'Shipment', 'logistics', 'packed as', 'Shipment is kept.');
    await wait(W_);
    await pConcept('Shipment', 'Carrier', 'logistics', 'handled by', 'Carrier is kept.');
    await wait(W_);
    await pConcept('Shipment', 'Route', 'logistics', 'follows', 'Route is kept.');
    await wait(W_);
    await pRelation('Shipment', 'leaves from', 'Warehouse', 'Shipment leaves from Warehouse: Logistics reads Supply chain’s Warehouse.');
  },
  5: async () => {
    caption('Quality and Maintenance · seven proposals', 'Two more domain products. Maintenance specialises a concept it does not own: a Machine due for maintenance is still Production’s Machine, now living in Maintenance’s colour.');
    await pConcept('Product', 'Inspection', 'quality', 'checked by', 'Inspection is kept in Quality.');
    await wait(W_);
    await pConcept('Inspection', 'Quality standard', 'quality', 'complies with', 'Quality standard is kept.');
    await wait(W_);
    await pConcept('Inspection', 'Defect', 'quality', 'records', 'Defect is kept.');
    await wait(W_);
    await pSpec('Machine', 'Machine due for maintenance', '> 5,000 h since last service', 'Machine divides across the boundary: Maintenance owns the specialisation, Production still owns Machine, and the dashed “is a” keeps the two tied.', 'maintenance');
    await wait(1050);
    await pConcept('Machine due for maintenance', 'Maintenance plan', 'maintenance', 'scheduled by', 'Maintenance plan is kept.');
    await wait(W_);
    await pConcept('Maintenance plan', 'Spare part', 'maintenance', 'needs', 'Spare part is kept.');
    await wait(W_);
    await pConcept('Machine', 'Sensor', 'maintenance', 'monitored by', 'Sensor is kept in Maintenance, attached to Production’s Machine.');
  },
  6: async () => {
    caption('Finance and People · six proposals', 'Controlling and HR publish their products too. Operator is an Employee: Production and People agree on who a person is.');
    await pConcept('Sales order', 'Invoice', 'finance', 'billed by', 'Invoice is kept in Finance.');
    await wait(W_);
    await pConcept('Plant', 'Cost centre', 'finance', 'charged to', 'Cost centre is kept.');
    await wait(W_);
    await pConcept('Cost centre', 'Budget', 'finance', 'limited by', 'Budget is kept.');
    await wait(W_);
    await pConcept('Northwind Industries', 'Employee', 'people', 'employs', 'Employee is kept in People.');
    await wait(W_);
    await pRelation('Operator', 'is a', 'Employee', 'Operator is an Employee: the same person seen by two domain products.');
    await wait(500);
    await pConcept('Employee', 'Certification', 'people', 'holds', 'Certification is kept.');
    await wait(W_);
    await pConcept('Certification', 'Training', 'people', 'earned through', 'Training is kept.');
  },
  7: async () => {
    caption('Engineering · four proposals', 'R&D owns the definition of what a pump is; Production builds it, Sales sells it, Quality checks it.');
    await pConcept('Product', 'Specification', 'engineering', 'specified by', 'Specification is kept in Engineering.');
    await wait(W_);
    await pConcept('Specification', 'Test', 'engineering', 'validated by', 'Test is kept.');
    await wait(W_);
    await pConcept('Specification', 'Engineering change', 'engineering', 'evolved by', 'Engineering change is kept.');
    await wait(W_);
    await pRelation('Engineering change', 'updates', 'Bill of materials', 'Engineering change updates Bill of materials: R&D writes into Supply chain’s product through a declared relation.');
  },
  8: async () => {
    caption('Two proposals', 'Two domain products define the same word. Approve both and watch what the model does.');
    await pSpec('Product', 'Defective product', 'failed inspection', 'Quality’s definition is in the model.', 'quality');
    await wait(1050);
    await pSpec('Product', 'Defective product', 'scrapped', 'Production’s definition is in the model too.', 'production');
  },
  9: async () => {
    const both = s.nodes.filter((n) => n.label === 'Defective product' && n.sid);
    if (both.length >= 2)
      await post({
        type: 'change',
        changeKind: 'resolve_conflict',
        payload: { conflictConceptIds: [both[0].sid as string, both[1].sid as string] },
        caption:
          'One business, two certified truths, each owned by its domain product. Quality keeps its definition, Production keeps its own name, and the model records that one is a kind of the other.',
      });
    caption('One proposal', 'The owners’ decision, as a change to approve.');
  },
  10: async () => {
    const c = s.companies[0];
    caption('Eight data sources', 'Systems arrive from outside the company, like the equivalences arrived from another company. Then each one asks to feed the concepts it holds.');
    const S: [string, string, string[]][] = [
      ['MES', 'manufacturing execution', ['Plant', 'Production line', 'Machine', 'Shift', 'Work order']],
      ['SAP ERP', 'ERP', ['Product', 'Bill of materials', 'Material', 'Supplier', 'Purchase order', 'Sales order', 'Invoice', 'Cost centre', 'Budget', 'Stock level']],
      ['Salesforce CRM', 'CRM', ['Customer', 'Sales region', 'Quotation', 'Price list']],
      ['WMS', 'warehouse management', ['Warehouse', 'Delivery', 'Shipment', 'Carrier', 'Route']],
      ['QMS', 'quality management', ['Inspection', 'Quality standard', 'Defect']],
      ['CMMS', 'maintenance management', ['Maintenance plan', 'Spare part', 'Sensor']],
      ['HRIS', 'HR system', ['Employee', 'Operator', 'Certification', 'Training']],
      ['PLM', 'product lifecycle', ['Specification', 'Test', 'Engineering change']],
    ];
    for (const [label, kind] of S) {
      await pSource(c, label, kind);
      await wait(260);
    }
    await wait(400);
    for (const [label, , concepts] of S) {
      await pBind(c, label, concepts);
      await wait(200);
    }
    caption('Sixteen proposals', 'Eight sources, then one binding per source. Approve a binding and the concepts light up with their record counts; attributes found in the schema but missing from the model queue up behind.');
  },
  11: async () => {
    if (!s.companies.find((c) => c.key === 'aurora-valves')) {
      caption('Aurora Valves joins the view', 'A second company, side by side, with its own domain products, owners and vocabulary. Nothing is merged; nothing is overwritten. Its starter vocabulary is waiting for approval.');
      await addCompany('Aurora Valves', 'industrial valves · 2 plants · 640 people', true);
    }
  },
  12: async () => {
    const a = s.companies.find((c) => c.key === 'aurora-valves'),
      n = s.companies[0];
    if (!a) return;
    s.activeCompany = n;
    store.renderCompanies();
    caption('Alignment · eight proposals', 'The private-equity view: one meaning, two vocabularies. Each equivalence is a dotted two-way line; both companies keep their own words and their own owners.');
    if (store.ui.settings && !store.ui.settings.crossCompany) {
      caption('Not allowed', 'Companies may not interact: the setting is off in the admin portal. Enable it to align vocabularies.');
      return;
    }
    for (const [x, y] of [
      ['Site', 'Plant'],
      ['Line', 'Production line'],
      ['Equipment', 'Machine'],
      ['Article', 'Product'],
      ['Component', 'Material'],
      ['Vendor', 'Supplier'],
      ['Client', 'Customer'],
      ['Client order', 'Sales order'],
      ['Non-conformity', 'Defect'],
    ]) {
      await pEquiv(x, a, y, n);
      await wait(380);
    }
  },
  13: async () => {
    const a = s.companies.find((c) => c.key === 'aurora-valves');
    if (!a) return;
    s.activeCompany = a;
    store.renderCompanies();
    if (!s.COVERAGE) store.toggleCoverage();
    await pSource(a, 'Sage X3', 'ERP');
    await wait(400);
    await pBind(a, 'Sage X3', ['Site', 'Line', 'Article', 'Client', 'Client order', 'Vendor'], 'Six of Aurora’s concepts have data behind them. The rest are words.');
    caption('Coverage on', 'Aurora Valves has one system. Bind it and read the picture: full cells have data, hollow cells are vocabulary without evidence. That is the diligence map.');
  },
  14: async () => {
    const pool: [string, string, string, DomainKey][] = [
      ['Batch', 'produced in', 'Work order', 'production'],
      ['Downtime', 'records', 'Machine', 'production'],
      ['Changeover', 'requires', 'Production line', 'production'],
      ['Tool', 'uses', 'Machine', 'production'],
      ['Scrap', 'generates', 'Work order', 'production'],
      ['Supplier contract', 'governed by', 'Supplier', 'supply'],
      ['Forecast', 'planned by', 'Material', 'supply'],
      ['Goods receipt', 'confirmed by', 'Purchase order', 'supply'],
      ['Lot', 'received as', 'Material', 'supply'],
      ['Discount', 'applies to', 'Price list', 'sales'],
      ['Contract', 'covered by', 'Customer', 'sales'],
      ['Opportunity', 'preceded by', 'Quotation', 'sales'],
      ['Packaging', 'requires', 'Shipment', 'logistics'],
      ['Customs declaration', 'needs', 'Shipment', 'logistics'],
      ['Return', 'reversed by', 'Delivery', 'logistics'],
      ['Corrective action', 'triggers', 'Defect', 'quality'],
      ['Audit', 'reviewed by', 'Quality standard', 'quality'],
      ['Customer complaint', 'raises', 'Defect', 'quality'],
      ['Alarm', 'raises', 'Sensor', 'maintenance'],
      ['Work permit', 'requires', 'Maintenance plan', 'maintenance'],
      ['Technician', 'performed by', 'Maintenance plan', 'maintenance'],
      ['Payment', 'settles', 'Invoice', 'finance'],
      ['Credit note', 'corrects', 'Invoice', 'finance'],
      ['Depreciation', 'charges', 'Cost centre', 'finance'],
      ['Skill', 'requires', 'Certification', 'people'],
      ['Absence', 'recorded for', 'Employee', 'people'],
      ['Safety incident', 'involves', 'Employee', 'people'],
      ['Prototype', 'built from', 'Specification', 'engineering'],
      ['Test report', 'produced by', 'Test', 'engineering'],
      ['Drawing', 'detailed in', 'Specification', 'engineering'],
    ];
    caption('Thirty proposals', 'A week across nine domain products. Approve them one by one, or all at once.');
    s.activeCompany = s.companies[0];
    store.renderCompanies();
    for (const [label, pred, parent, dom] of pool) {
      if (store.findNode(parent, s.companies[0])) await pConcept(parent, label, dom, pred, undefined, s.companies[0]);
      await wait(REDUCED ? 150 : 320);
    }
  },
};

/** Plays scene `i`: header, placeholder sentence, then the scene's proposals. */
export async function playScene(i: number): Promise<void> {
  if (s.running || !SCENES[i] || !runs[i]) return;
  s.running = true;
  store.setScene(i);
  void api.putViewState({ sceneIdx: i }).catch(() => undefined);
  if (!/Acqui|Align|Diligence/.test(SCENES[i].name) && s.companies[0]) {
    s.activeCompany = s.companies[0];
    store.renderCompanies();
  }
  store.ui.say = '';
  store.ui.sayPlaceholder = `“${SCENES[i].say}”`;
  store.bump();
  try {
    await runs[i]();
  } finally {
    s.running = false;
    store.bump();
  }
}

export function next(): void {
  if (store.ui.sceneIdx < SCENES.length - 1) void playScene(store.ui.sceneIdx + 1);
}

let finalising = false;

/** Plays every remaining scene with animations off and approves everything. */
export async function finaliseAll(): Promise<void> {
  if (finalising) return;
  finalising = true;
  store.ui.finalising = true;
  store.bump();
  const wasSkip = s.SKIP;
  if (!s.SKIP) store.toggleSkip();
  try {
    for (let i = store.ui.sceneIdx + 1; i < SCENES.length; i++) {
      await playScene(i);
      await api.approveAll();
      await wait(0);
    }
    const res = await api.finaliseAll();
    store.caption('Finalised', res.caption || 'Everything approved.');
    store.toast2('Finalised', `${res.concepts} concepts approved`);
  } finally {
    if (s.SKIP !== wasSkip) store.toggleSkip();
    finalising = false;
    store.ui.finalising = false;
    store.bump();
  }
}

/**
 * Teaching: an empty sentence plays the next scene, a sentence matching the coming scene plays
 * it, anything else is parsed by the API into proposal drafts. Ported from
 * reference/ontaix-studio-reference.html lines 864-884 (`teach`). Sentences from a document
 * import skip the story interception.
 */
export async function teach(text: string, fromImport = false): Promise<void> {
  text = text.trim();
  if (!text) return fromImport ? undefined : next();
  const up = SCENES[store.ui.sceneIdx + 1];
  if (!fromImport && up && up.match && up.match.test(text)) return playScene(store.ui.sceneIdx + 1);
  const co = s.activeCompany;
  if (!co || !co.sid) return;
  const result = await api.teachParse({ companyId: co.sid, text, fromImport });
  if (result.outcome === 'scene') return playScene(store.ui.sceneIdx + 1);
  if (result.outcome === 'understood') {
    await api.createProposalBatch(result.drafts.map(withSeed)).catch((err) => store.refused(err));
    const n = result.statements?.length ?? result.drafts.length;
    store.caption(`Understood ${n === 1 ? 'one statement' : n + ' statements'}`, result.caption);
    return;
  }
  if (result.outcome === 'partly_understood') {
    result.drafts.forEach((d, i) => setTimeout(() => void store.propose(withSeed(d)), i * 850));
    store.caption('Partly understood', result.caption);
    return;
  }
  store.caption('Not understood', result.caption);
}

/** Text of an imported file; CSV rows become sentences. Word and PDF need libraries the Studio does not ship. */
async function textOf(file: File): Promise<string> {
  const name = file.name.toLowerCase();
  if (name.endsWith('.docx') || name.endsWith('.pdf')) throw new Error('Word and PDF import is not available yet');
  if (name.endsWith('.csv')) {
    const raw = await file.text();
    return raw
      .split(/\r?\n/)
      .map((r) =>
        r
          .split(/[;,\t]/)
          .map((c) => c.trim())
          .filter(Boolean)
          .join(' '),
      )
      .join('. ');
  }
  return await file.text();
}

export function sentencesOf(text: string): string[] {
  return text
    .replace(/\s+/g, ' ')
    .split(/(?<=[.!?])\s+|\n+/)
    .map((x) => x.trim())
    .filter((x) => x.length > 12 && x.length < 400);
}

/** Import a document: every sentence is read like a spoken one. Reference lines 897-903. */
export async function importDocument(file: File | null | undefined): Promise<void> {
  if (!file || store.ui.importing) return;
  store.ui.importing = true;
  store.bump();
  try {
    const text = await textOf(file);
    const sents = sentencesOf(text);
    const before = store.ui.proposals.length;
    store.caption(
      'Importing ' + file.name,
      `${sents.length} sentences found. Each one is read the way a spoken sentence is; what the model understands becomes a proposal.`,
    );
    for (const sn of sents) {
      await teach(sn, true);
      await wait(s.SKIP ? 0 : 450);
    }
    await store.refreshProposals();
    const added = store.ui.proposals.length - before;
    store.caption(
      'Import finished',
      `${file.name}: ${sents.length} sentences read, ${added} proposal${added === 1 ? '' : 's'} waiting for approval on the right.`,
    );
  } catch (err) {
    store.caption(
      'Import failed',
      `${file.name} could not be read (${(err as Error).message}). Text, Markdown, CSV, Word and PDF are supported.`,
    );
  } finally {
    store.ui.importing = false;
    store.bump();
  }
}
