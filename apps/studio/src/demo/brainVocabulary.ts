/**
 * Names for the demo brain's concepts: what a pump maker's domains talk about, so a close look
 * at the grown brain reads as a credible model. Each domain combines its own nouns with
 * qualifiers; a custom domain uses general business nouns. Once every combination of a domain
 * is used, names come back for one plant after another (`Shipment · Porto`), then with a number.
 */
import { seeded } from './brainShape';

/** Key of the brain stem's vocabulary: what the company as a whole is made of. */
export const CORE_KEY = 'core';

const NOUNS: Record<string, string[]> = {
  [CORE_KEY]: ['Business capability', 'Value stream', 'Site', 'Legal entity', 'Business unit', 'Strategic goal', 'Company policy', 'Business rule', 'Product family', 'Market', 'Brand', 'Programme'],
  production: ['Work order', 'Production line', 'Batch', 'Routing', 'Shift', 'Work centre', 'Bill of materials', 'Casting', 'Machining step', 'Assembly', 'Test bench', 'Scrap record', 'Setup time', 'Yield', 'Operator', 'Tooling'],
  supply: ['Supplier', 'Purchase order', 'Raw material', 'Impeller blank', 'Motor', 'Seal kit', 'Bearing', 'Contract', 'Lead time', 'Goods receipt', 'Supplier rating', 'Price agreement', 'Forecast', 'Reorder point', 'Sourcing plan', 'Invoice'],
  sales: ['Customer', 'Sales order', 'Quote', 'Opportunity', 'Price list', 'Discount', 'Key account', 'Distributor', 'Tender', 'Order line', 'Sales region', 'Commission', 'Contract renewal', 'Product configuration', 'Lead', 'Campaign'],
  logistics: ['Delivery', 'Shipment', 'Carrier', 'Warehouse', 'Pallet', 'Route', 'Pick list', 'Customs declaration', 'Freight cost', 'Dock slot', 'Tracking event', 'Stock location', 'Packing unit', 'Proof of delivery', 'Return', 'Transit time'],
  quality: ['Inspection', 'Defect', 'Non-conformance', 'Test result', 'Certificate', 'Audit', 'Corrective action', 'Tolerance', 'Calibration', 'Complaint', 'Root cause', 'Sample plan', 'Pressure test', 'Leak test', 'Quality gate', 'Deviation'],
  maintenance: ['Asset', 'Work request', 'Spare part', 'Service visit', 'Failure mode', 'Maintenance plan', 'Vibration reading', 'Downtime', 'Technician', 'Warranty claim', 'Inspection round', 'Lubrication task', 'Repair', 'Meter reading', 'Service contract', 'Installed base'],
  finance: ['Cost centre', 'Invoice', 'Payment', 'Budget', 'Ledger account', 'Margin', 'Credit limit', 'Cash forecast', 'Standard cost', 'Variance', 'Tax code', 'Accrual', 'Profit centre', 'Exchange rate', 'Write-off', 'Revenue'],
  people: ['Employee', 'Team', 'Role', 'Skill', 'Training', 'Certification', 'Shift plan', 'Absence', 'Position', 'Contract', 'Review', 'Safety briefing', 'Recruitment', 'Onboarding', 'Time sheet', 'Competence'],
  engineering: ['Pump model', 'Impeller design', 'Drawing', 'Specification', 'Change request', 'Prototype', 'Simulation', 'Material spec', 'Performance curve', 'Design review', 'Variant', 'Revision', 'Test plan', 'Efficiency class', 'Standard part', 'Patent'],
};

const QUALIFIERS: Record<string, string[]> = {
  [CORE_KEY]: ['', 'Group', 'European', 'Americas', 'Core', 'Emerging', 'Shared', 'Future'],
  production: ['', 'Planned', 'Rework', 'Night', 'Line 2', 'Pilot', 'Serial', 'Urgent'],
  supply: ['', 'Strategic', 'Local', 'Backup', 'Framework', 'Spot', 'Certified', 'Asian'],
  sales: ['', 'Export', 'Strategic', 'Service', 'Framework', 'Retail', 'OEM', 'Public'],
  logistics: ['', 'Inbound', 'Outbound', 'Express', 'Sea', 'Road', 'Bonded', 'Cross-dock'],
  quality: ['', 'Incoming', 'Final', 'Supplier', 'Customer', 'In-process', 'Annual', 'Critical'],
  maintenance: ['', 'Preventive', 'Corrective', 'Predictive', 'Field', 'Remote', 'Annual', 'Emergency'],
  finance: ['', 'Planned', 'Actual', 'Monthly', 'Group', 'Local', 'Forecast', 'Year-end'],
  people: ['', 'Plant', 'Field', 'Temporary', 'Senior', 'Apprentice', 'Regional', 'Night shift'],
  engineering: ['', 'Draft', 'Released', 'Legacy', 'Next-generation', 'Customer', 'High-pressure', 'Compact'],
};

/** The plants a repeated name belongs to, in order. */
const PLANTS = ['Lyon', 'Porto', 'Gdańsk', 'Monterrey', 'Pune', 'Turin', 'Leeds', 'Ohio', 'Brno', 'Izmir'];

const GENERAL = ['Record', 'Process', 'Policy', 'Agreement', 'Request', 'Plan', 'Report', 'Event', 'Rule', 'Register', 'Review', 'Metric'];
const GENERAL_QUALIFIERS = ['', 'Draft', 'Approved', 'Annual', 'Local', 'Group', 'Open', 'Archived'];

/**
 * A name source for one domain: `next()` returns a fresh concept name each call. `domainName`
 * prefixes the general nouns of a custom domain.
 */
export function namesFor(domainKey: string, domainName: string, seed: number): { next(): string } {
  const rand = seeded(seed);
  const nouns = NOUNS[domainKey] ?? GENERAL.map((n) => `${domainName} ${n.toLowerCase()}`);
  const quals = QUALIFIERS[domainKey] ?? GENERAL_QUALIFIERS;
  const all: string[] = [];
  for (const q of quals) for (const n of nouns) all.push(q ? `${q} ${n.charAt(0).toLowerCase()}${n.slice(1)}` : n);
  // Plain nouns come first, so the first cells of a domain carry its core vocabulary.
  const plain = all.slice(0, nouns.length);
  const rest = all.slice(nouns.length);
  for (let i = rest.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [rest[i], rest[j]] = [rest[j], rest[i]];
  }
  const deck = [...plain, ...rest];
  let i = 0;
  return {
    next() {
      const round = Math.floor(i / deck.length);
      const name = deck[i % deck.length];
      i++;
      if (!round) return name;
      const plant = PLANTS[(round - 1) % PLANTS.length],
        lap = Math.floor((round - 1) / PLANTS.length);
      return `${name} · ${plant}${lap ? ` ${lap + 1}` : ''}`;
    },
  };
}
