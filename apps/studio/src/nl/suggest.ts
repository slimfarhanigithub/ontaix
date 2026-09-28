/**
 * Suggest an action from two names: a guess to edit, never submitted. Ported from
 * reference/ontaix-studio-reference.html lines 670-684 (`DOES`, `DONE_TO`, `mostCommon`,
 * `suggestAction`).
 */
import type { SceneState } from '../canvas/state';
import type { Node } from '../canvas/types';

/** What a subject typically does, keyed on the subject's name. */
export const DOES: [RegExp, string][] = [
  [/discount|promotion|coupon|rebate|price list|tariff|rate/, 'applies to'],
  [/customer|client|account|buyer/, 'places'],
  [/supplier|vendor|carrier|provider/, 'supplies'],
  [/order|requisition|quotation|request|demand/, 'contains'],
  [/invoice|bill|payment|credit note|ledger/, 'bills'],
  [/inspection|test|audit|check|review/, 'checks'],
  [/plan|schedule|forecast|calendar/, 'schedules'],
  [/standard|policy|rule|regulation|norm|contract|specification/, 'governs'],
  [/warehouse|store|depot|site|plant|location/, 'stores'],
  [/shipment|delivery|route|transport/, 'delivers'],
  [/employee|operator|staff|technician|worker|team/, 'works on'],
  [/sensor|meter|gauge|monitor/, 'monitors'],
  [/alarm|defect|incident|complaint|non-conformity|claim/, 'concerns'],
  [/machine|equipment|asset|line|tool|robot/, 'produces'],
  [/material|component|part|ingredient/, 'used in'],
  [/product|article|item|good|sku/, 'sold as'],
  [/certification|training|skill|qualification/, 'qualifies'],
  [/report|document|drawing|record/, 'describes'],
  [/budget|cost centre|fund/, 'funds'],
  [/shift|batch|lot|campaign|run/, 'produces'],
  [/region|category|family|segment|group/, 'groups'],
  [/bill of materials|bom|recipe|formula/, 'defines'],
  [/work order|job|task|ticket/, 'executes on'],
];

/** What is typically done to an object, keyed on the object's name. */
export const DONE_TO: [RegExp, string][] = [
  [/order|requisition|quotation|request/, 'places'],
  [/line|machine|equipment|asset|tool|sensor/, 'has'],
  [/material|component|part|ingredient/, 'uses'],
  [/product|article|item|good/, 'produces'],
  [/customer|client|account/, 'serves'],
  [/supplier|vendor|carrier/, 'bought from'],
  [/plan|schedule|forecast|budget/, 'scheduled by'],
  [/inspection|test|audit|check/, 'checked by'],
  [/invoice|payment|credit note|ledger/, 'billed by'],
  [/employee|operator|staff|technician|worker/, 'staffed by'],
  [/warehouse|site|plant|store|location/, 'located in'],
  [/report|document|specification|drawing|contract/, 'described by'],
  [/defect|incident|alarm|non-conformity|complaint/, 'raises'],
  [/delivery|shipment|route/, 'shipped as'],
  [/certification|training|skill/, 'requires'],
  [/shift|batch|lot|campaign/, 'runs in'],
  [/region|category|family|segment/, 'grouped in'],
  [/cost centre|account/, 'charged to'],
  [/standard|policy|rule|regulation|norm/, 'complies with'],
  [/bill of materials|bom|recipe/, 'defined by'],
  [/discount|promotion|coupon/, 'eligible for'],
];

export const mostCommon = (arr: string[]): string | null => {
  const m: Record<string, number> = {};
  for (const x of arr) m[x] = (m[x] || 0) + 1;
  return Object.entries(m).sort((a, b) => b[1] - a[1])[0]?.[0] || null;
};

export function suggestAction(
  s: SceneState,
  subject: string,
  object: string,
  subjNode: Node | null,
  objNode: Node | null,
): string {
  const o = (object || '').toLowerCase(),
    su = (subject || '').toLowerCase();
  // 1. what this subject already does toward things like the object (same domain), then toward anything
  if (subjNode && objNode) {
    const out = mostCommon(
      s.links
        .filter((l) => l.a === subjNode && l.kind === 'rel' && l.b.domain === objNode.domain && l.b !== objNode)
        .map((l) => l.label),
    );
    if (out) return out;
  }
  // 2. what a subject with this name typically does
  for (const [re, v] of DOES) if (re.test(su)) return v;
  // 3. what is typically done to an object with this name
  for (const [re, v] of DONE_TO) if (re.test(o)) return v;
  // 4. what the subject does to anything, then what others do to the object
  if (subjNode) {
    const out = mostCommon(s.links.filter((l) => l.a === subjNode && l.kind === 'rel').map((l) => l.label));
    if (out) return out;
  }
  if (objNode) {
    const inc = mostCommon(s.links.filter((l) => l.b === objNode && l.kind === 'rel').map((l) => l.label));
    if (inc) return inc;
  }
  return 'relates to';
}
