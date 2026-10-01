/**
 * Models for the arrange tests and measurements: the fixture model (Northwind Industries taught
 * domain by domain, Aurora Valves with its starter vocabulary, nine equivalences between them),
 * the same rows the API seeds with `ONTAIX_SEED=fixture`, and a seeded synthetic model of any
 * size. Cells are placed where they were born, as division leaves them before physics settles.
 */
import { mulberry32 } from '../runtime/mulberry32';
import { addCompany, addLink, addNode, domainCentre, domainOf, find, type SceneState } from './state';
import type { Company, Node } from './types';

type Row =
  | { k: 'concept'; parent: string; label: string; domain: string; action: string }
  | { k: 'spec'; parent: string; label: string; rule: string; domain: string }
  | { k: 'relation'; subject: string; action: string; object: string };

const NW = 'Northwind Industries';
const c = (parent: string, label: string, domain: string, action: string): Row => ({ k: 'concept', parent, label, domain, action });
const r = (subject: string, action: string, object: string): Row => ({ k: 'relation', subject, action, object });

/** Northwind Industries, batch by batch, as `apps/api/app/seed/northwind.py` lists it. */
const NORTHWIND: Row[] = [
  c(NW, 'Plant', 'production', 'operates'),
  c('Plant', 'Production line', 'production', 'runs'),
  c('Production line', 'Machine', 'production', 'has'),
  c('Production line', 'Shift', 'production', 'runs in'),
  c('Shift', 'Operator', 'production', 'staffed by'),
  c('Production line', 'Work order', 'production', 'executes'),
  c('Work order', 'Product', 'production', 'produces'),
  c('Product', 'Bill of materials', 'supply', 'defined by'),
  c('Bill of materials', 'Material', 'supply', 'lists'),
  c('Material', 'Supplier', 'supply', 'bought from'),
  c('Supplier', 'Purchase order', 'supply', 'receives'),
  c('Material', 'Warehouse', 'supply', 'stored in'),
  c('Warehouse', 'Stock level', 'supply', 'tracks'),
  c(NW, 'Customer', 'sales', 'serves'),
  c('Customer', 'Sales region', 'sales', 'grouped in'),
  c('Customer', 'Quotation', 'sales', 'requests'),
  c('Quotation', 'Sales order', 'sales', 'becomes'),
  c('Sales order', 'Price list', 'sales', 'priced from'),
  r('Sales order', 'contains', 'Product'),
  r('Sales order', 'triggers', 'Work order'),
  c('Sales order', 'Delivery', 'logistics', 'fulfilled by'),
  c('Delivery', 'Shipment', 'logistics', 'packed as'),
  c('Shipment', 'Carrier', 'logistics', 'handled by'),
  c('Shipment', 'Route', 'logistics', 'follows'),
  r('Shipment', 'leaves from', 'Warehouse'),
  c('Product', 'Inspection', 'quality', 'checked by'),
  c('Inspection', 'Quality standard', 'quality', 'complies with'),
  c('Inspection', 'Defect', 'quality', 'records'),
  { k: 'spec', parent: 'Machine', label: 'Machine due for maintenance', rule: '> 5,000 h since last service', domain: 'maintenance' },
  c('Machine due for maintenance', 'Maintenance plan', 'maintenance', 'scheduled by'),
  c('Maintenance plan', 'Spare part', 'maintenance', 'needs'),
  c('Machine', 'Sensor', 'maintenance', 'monitored by'),
  c('Sales order', 'Invoice', 'finance', 'billed by'),
  c('Plant', 'Cost centre', 'finance', 'charged to'),
  c('Cost centre', 'Budget', 'finance', 'limited by'),
  c(NW, 'Employee', 'people', 'employs'),
  r('Operator', 'is a', 'Employee'),
  c('Employee', 'Certification', 'people', 'holds'),
  c('Certification', 'Training', 'people', 'earned through'),
  c('Product', 'Specification', 'engineering', 'specified by'),
  c('Specification', 'Test', 'engineering', 'validated by'),
  c('Specification', 'Engineering change', 'engineering', 'evolved by'),
  r('Engineering change', 'updates', 'Bill of materials'),
];

const AV = 'Aurora Valves';
/** The thirteen-concept starter vocabulary, as `apps/api/app/seed/starter_vocabulary.py` lists it. */
const AURORA: Row[] = [
  c(AV, 'Site', 'production', 'operates'),
  c('Site', 'Line', 'production', 'runs'),
  c('Line', 'Equipment', 'production', 'has'),
  c('Line', 'Article', 'production', 'produces'),
  c('Article', 'Component', 'supply', 'uses'),
  c('Component', 'Vendor', 'supply', 'bought from'),
  c('Component', 'Purchase requisition', 'supply', 'requested by'),
  c(AV, 'Client', 'sales', 'serves'),
  c('Client', 'Client order', 'sales', 'places'),
  c('Article', 'Non-conformity', 'quality', 'raises'),
  c('Equipment', 'Field service', 'maintenance', 'serviced by'),
  c(AV, 'Staff member', 'people', 'employs'),
  c('Client order', 'Ledger entry', 'finance', 'posted by'),
];

/** Aurora label and the Northwind label it is the same concept as (`apps/api/app/seed/aurora.py`). */
const EQUIVALENCES: [string, string][] = [
  ['Site', 'Plant'],
  ['Line', 'Production line'],
  ['Equipment', 'Machine'],
  ['Article', 'Product'],
  ['Component', 'Material'],
  ['Vendor', 'Supplier'],
  ['Client', 'Customer'],
  ['Client order', 'Sales order'],
  ['Non-conformity', 'Defect'],
];

function grow(s: SceneState, company: Company, rows: Row[], rnd: () => number): void {
  const get = (label: string): Node => {
    const n = label === company.name ? company.root : find(s, label, company);
    if (!n) throw new Error(`unknown concept ${label}`);
    return n;
  };
  for (const row of rows) {
    if (row.k === 'relation') {
      addLink(s, get(row.subject), get(row.object), row.action === 'is a' ? 'isa' : 'rel', 230, row.action, rnd());
      continue;
    }
    const parent = get(row.parent);
    const d = domainOf(s, row.domain, company);
    const [gx, gy] = d ? domainCentre(d) : [company.x, company.y];
    const n = addNode(s, {
      label: row.label,
      domain: d,
      company,
      color: d ? d.color : parent.color,
      x: gx + (rnd() - 0.5) * 160,
      y: gy + (rnd() - 0.5) * 160,
      alpha: 1,
      seed: rnd() * 100,
    });
    n.parent = parent;
    if (row.k === 'spec') {
      n.sub = row.rule;
      n.birthLink = addLink(s, n, parent, 'isa', 170, 'is a', rnd());
    } else {
      n.birthLink = addLink(s, parent, n, 'rel', 220, row.action, rnd());
    }
  }
}

/** Northwind Industries alone, every batch approved. */
export function northwindModel(s: SceneState, seed = 7): Company {
  const rnd = mulberry32(seed);
  const nw = addCompany(s, NW, 'industrial pumps · 4 plants · 2,300 people');
  grow(s, nw, NORTHWIND, rnd);
  return nw;
}

/** The fixture model: Northwind Industries, Aurora Valves and the nine equivalences. */
export function fixtureModel(s: SceneState, seed = 7): { northwind: Company; aurora: Company } {
  const rnd = mulberry32(seed);
  const northwind = addCompany(s, NW, 'industrial pumps · 4 plants · 2,300 people');
  const aurora = addCompany(s, AV, 'industrial valves · 2 plants · 640 people');
  grow(s, northwind, NORTHWIND, rnd);
  grow(s, aurora, AURORA, rnd);
  for (const [a, b] of EQUIVALENCES)
    addLink(s, find(s, a, aurora) as Node, find(s, b, northwind) as Node, 'same', 230, 'equivalent to', rnd());
  return { northwind, aurora };
}

const WORDS = [
  'Asset', 'Contract', 'Order line', 'Batch', 'Work centre', 'Inspection lot', 'Route', 'Tariff',
  'Account', 'Ledger', 'Vehicle', 'Driver', 'Claim', 'Policy', 'Patient referral', 'Ward',
  'Recipe', 'Sample', 'Permit', 'Container', 'Customs declaration', 'Return', 'Service level',
];
const ACTIONS = ['has', 'owns', 'feeds', 'records', 'is planned by', 'ships', 'checked by', 'belongs to', 'raises', 'produces'];

/**
 * A seeded synthetic model of `size` concepts in one company: a birth tree in which a child stays
 * in its parent's domain three times in four, and one extra relation per `per` concepts (none
 * when `per` is 0).
 */
export function syntheticModel(s: SceneState, size: number, seed = 11, per = 8): Company {
  const rnd = mulberry32(seed);
  const company = addCompany(s, 'Synthetic Holdings', '');
  const keys = company.domains.map((d) => d.key);
  const made: Node[] = [];
  for (let i = 0; i < size; i++) {
    const parent = made.length && rnd() > 0.06 ? made[Math.floor(Math.pow(rnd(), 0.7) * made.length)] : (company.root as Node);
    const key = parent.domain && rnd() < 0.75 ? parent.domain.key : keys[Math.floor(rnd() * keys.length)];
    const d = domainOf(s, key, company);
    const [gx, gy] = domainCentre(d!);
    const n = addNode(s, {
      label: `${WORDS[Math.floor(rnd() * WORDS.length)]} ${i}`,
      domain: d,
      company,
      color: d!.color,
      x: gx + (rnd() - 0.5) * 200,
      y: gy + (rnd() - 0.5) * 200,
      alpha: 1,
      seed: rnd() * 100,
    });
    n.parent = parent;
    n.birthLink = addLink(s, parent, n, 'rel', 220, ACTIONS[Math.floor(rnd() * ACTIONS.length)], rnd());
    made.push(n);
  }
  for (let i = 0; i < (per ? Math.floor(size / per) : 0); i++) {
    const a = made[Math.floor(rnd() * made.length)],
      b = made[Math.floor(rnd() * made.length)];
    if (a !== b && !s.links.some((l) => (l.a === a && l.b === b) || (l.a === b && l.b === a)))
      addLink(s, a, b, 'rel', 230, ACTIONS[Math.floor(rnd() * ACTIONS.length)], rnd());
  }
  return company;
}

/** Moves every cell to the end of its arrange tween, as the animation leaves it. */
export function settleTweens(s: SceneState): void {
  for (const n of s.nodes)
    if (n.tween) {
      n.x = n.tween.tx;
      n.y = n.tween.ty;
      n.tween = null;
    }
}
