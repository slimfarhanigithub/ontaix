/**
 * The fifteen scenes of the scripted story: name, the sentence shown as the teach placeholder,
 * and the pattern that intercepts a typed sentence. Verbatim from
 * reference/ontaix-studio-reference.html lines 738-834; the proposals each scene creates live
 * in story.ts.
 */
import type { DemoScene } from '../api/types';

export interface SceneMeta {
  name: string;
  say?: string;
  match?: RegExp;
}

export const SCENES: SceneMeta[] = [
  { name: 'Northwind Industries, before it knows itself' },
  {
    name: 'Production',
    say: 'We run four plants with production lines. Each line has machines, runs in shifts staffed by operators, and executes work orders that produce our pumps.',
    match: /plant|production line|machine|shift/i,
  },
  {
    name: 'Supply chain',
    say: 'Products are defined by a bill of materials. Materials are bought from suppliers through purchase orders, stored in warehouses, and tracked as stock levels.',
    match: /material|supplier|purchase|warehouse|stock/i,
  },
  {
    name: 'Sales',
    say: 'We serve customers grouped in sales regions. A quotation becomes a sales order, priced from a price list. A sales order contains products and triggers work orders.',
    match: /customer|sales order|quotation|price/i,
  },
  {
    name: 'Logistics',
    say: 'Each sales order is fulfilled by a delivery. A delivery is a shipment handled by a carrier along a route.',
    match: /delivery|shipment|carrier|route/i,
  },
  {
    name: 'Quality and maintenance',
    say: 'Every product is checked by an inspection against a quality standard; failures are recorded as defects. A machine that has run more than five thousand hours since its last service is due for maintenance and gets a maintenance plan with spare parts and sensors.',
    match: /inspection|defect|maintenance|hours|sensor/i,
  },
  {
    name: 'Finance and people',
    say: 'Sales orders are billed by invoices. Each plant is charged to a cost centre with a budget. Operators are employees who hold certifications earned through training.',
    match: /invoice|cost centre|budget|employee|training|certification/i,
  },
  {
    name: 'Engineering',
    say: 'Every product is specified by an engineering specification, validated by a test, and evolved through engineering changes.',
    match: /specification|engineering|test|design/i,
  },
  {
    name: 'Two products, one word',
    say: 'In quality, a defective product is any product that failed inspection. In production, a defective product is any product that was scrapped.',
    match: /defective|scrap|failed/i,
  },
  {
    name: 'Resolution',
    say: 'Keep both. A scrapped product is a kind of defective product.',
    match: /keep|both|kind of/i,
  },
  {
    name: 'Wired to reality',
    say: 'Connect the model to our systems: MES, SAP, Salesforce, the warehouse, quality, maintenance, HR and PLM.',
    match: /connect|system|sap|mes|wired|bind/i,
  },
  {
    name: 'Acquisition',
    say: 'We acquire Aurora Valves. It joins the view with its own domain products and its own words.',
    match: /acqui|aurora|buy|merge/i,
  },
  {
    name: 'Align vocabularies',
    say: 'Site means Plant, Article means Product, Client means Customer. Align the two vocabularies without changing either.',
    match: /align|means|equivalent|same/i,
  },
  {
    name: 'Due diligence',
    say: 'Connect Aurora to its ERP and show me what is real.',
    match: /diligence|aurora.*erp|what is real|coverage/i,
  },
  {
    name: 'It keeps learning',
    say: 'And it keeps learning, every day, from every domain.',
    match: /keeps|learning|every/i,
  },
];

/** The scene list in the shape `GET /demo/scenes` returns it. */
export const demoScenes = (): DemoScene[] =>
  SCENES.map((sc, index) => ({ index, name: sc.name, say: sc.say ?? '', match: sc.match ? sc.match.source : '' }));
