/**
 * Fixture data of the in-browser mock API, verbatim from reference/ontaix-studio-reference.html:
 * `SEED` (line 612), `ATTR` (280-297), `generic` (298-299), `RECORDS` (300), `CATALOG`
 * (911-913), `DISCOVER` (1054) and the home company of `reset()` (736).
 */
import type { DomainKey } from '../types';

export const HOME_COMPANY = { name: 'Northwind Industries', sub: 'industrial pumps · 4 plants · 2,300 people' };

/** Starter vocabulary: child, domain, action, parent (null means the company root). */
export const SEED: [string, DomainKey, string, string | null][] = [
  ['Site', 'production', 'operates', null],
  ['Line', 'production', 'runs', 'Site'],
  ['Equipment', 'production', 'has', 'Line'],
  ['Article', 'production', 'produces', 'Line'],
  ['Component', 'supply', 'uses', 'Article'],
  ['Vendor', 'supply', 'bought from', 'Component'],
  ['Purchase requisition', 'supply', 'requested by', 'Component'],
  ['Client', 'sales', 'serves', null],
  ['Client order', 'sales', 'places', 'Client'],
  ['Non-conformity', 'quality', 'raises', 'Article'],
  ['Field service', 'maintenance', 'serviced by', 'Equipment'],
  ['Staff member', 'people', 'employs', null],
  ['Ledger entry', 'finance', 'posted by', 'Client order'],
];

/** name, type, column, fill percent, and `new` for attributes discovered but not yet in the model. */
export type AttrSpec = [string, string, string, number, 'new'?];

export const ATTR: Record<string, AttrSpec[]> = {
  Plant: [
    ['plant_id', 'id', 'mes.plant.id', 100],
    ['name', 'text', 'mes.plant.name', 100],
    ['country', 'text', 'mes.plant.country', 100],
    ['timezone', 'text', 'mes.plant.tz', 100, 'new'],
  ],
  'Production line': [
    ['line_id', 'id', 'mes.line.id', 100],
    ['plant_id', 'ref', 'mes.line.plant_id', 100],
    ['capacity_per_shift', 'number', 'mes.line.cap', 97],
    ['oee_target', 'number', 'mes.line.oee_t', 61, 'new'],
  ],
  Machine: [
    ['machine_id', 'id', 'mes.asset.id', 100],
    ['line_id', 'ref', 'mes.asset.line_id', 99],
    ['model', 'text', 'mes.asset.model', 96],
    ['running_hours', 'number', 'mes.asset.run_h', 98],
    ['last_service_date', 'date', 'mes.asset.last_svc', 88, 'new'],
  ],
  'Work order': [
    ['wo_number', 'id', 'mes.wo.no', 100],
    ['line_id', 'ref', 'mes.wo.line_id', 100],
    ['quantity', 'number', 'mes.wo.qty', 100],
    ['status', 'text', 'mes.wo.status', 100],
    ['due_date', 'date', 'mes.wo.due', 93],
  ],
  Product: [
    ['material_no', 'id', 'sap.mara.matnr', 100],
    ['description', 'text', 'sap.makt.maktx', 100],
    ['weight_kg', 'number', 'sap.mara.brgew', 91],
    ['product_family', 'text', 'sap.mara.prdha', 77, 'new'],
  ],
  Customer: [
    ['customer_id', 'id', 'crm.account.id', 100],
    ['name', 'text', 'crm.account.name', 100],
    ['segment', 'text', 'crm.account.segment', 82],
    ['email', 'text', 'crm.contact.email', 94, 'new'],
    ['credit_limit', 'number', 'sap.knb1.klimk', 64, 'new'],
  ],
  'Sales order': [
    ['order_no', 'id', 'sap.vbak.vbeln', 100],
    ['customer_id', 'ref', 'sap.vbak.kunnr', 100],
    ['net_value', 'number', 'sap.vbak.netwr', 100],
    ['order_date', 'date', 'sap.vbak.erdat', 100],
  ],
  Supplier: [
    ['vendor_id', 'id', 'sap.lfa1.lifnr', 100],
    ['name', 'text', 'sap.lfa1.name1', 100],
    ['country', 'text', 'sap.lfa1.land1', 99],
    ['payment_terms', 'text', 'sap.lfb1.zterm', 71, 'new'],
  ],
  Material: [
    ['material_no', 'id', 'sap.mara.matnr', 100],
    ['base_unit', 'text', 'sap.mara.meins', 100],
    ['lead_time_days', 'number', 'sap.marc.plifz', 83],
  ],
  Employee: [
    ['employee_id', 'id', 'hris.person.id', 100],
    ['full_name', 'text', 'hris.person.name', 100],
    ['job_title', 'text', 'hris.position.title', 98],
    ['site', 'ref', 'hris.person.site', 96],
    ['cost_centre', 'ref', 'hris.person.cc', 88, 'new'],
  ],
  Inspection: [
    ['inspection_id', 'id', 'qms.insp.id', 100],
    ['product_ref', 'ref', 'qms.insp.matnr', 100],
    ['result', 'text', 'qms.insp.result', 100],
    ['inspector', 'ref', 'qms.insp.user', 79, 'new'],
  ],
  Defect: [
    ['defect_id', 'id', 'qms.defect.id', 100],
    ['code', 'text', 'qms.defect.code', 100],
    ['severity', 'text', 'qms.defect.sev', 92],
  ],
  'Maintenance plan': [
    ['plan_id', 'id', 'cmms.plan.id', 100],
    ['asset_id', 'ref', 'cmms.plan.asset', 100],
    ['interval_hours', 'number', 'cmms.plan.int_h', 95],
    ['next_due', 'date', 'cmms.plan.next', 90, 'new'],
  ],
  Site: [
    ['site_code', 'id', 'x3.facility.fcy', 100],
    ['name', 'text', 'x3.facility.name', 100],
    ['region', 'text', 'x3.facility.reg', 54, 'new'],
  ],
  Article: [
    ['item_ref', 'id', 'x3.item.itmref', 100],
    ['description', 'text', 'x3.item.desc', 100],
    ['unit', 'text', 'x3.item.stu', 100],
  ],
  Client: [
    ['bp_number', 'id', 'x3.bp.bpcnum', 100],
    ['name', 'text', 'x3.bp.bpcnam', 100],
    ['country', 'text', 'x3.bp.cry', 88],
    ['vat_number', 'text', 'x3.bp.eecnum', 41, 'new'],
  ],
};

export const slug = (l: string): string => l.toLowerCase().replace(/\s+/g, '_');

export const generic = (label: string): AttrSpec[] => [
  [slug(label) + '_id', 'id', 'src.' + slug(label) + '.id', 100],
  ['name', 'text', 'src.' + slug(label) + '.name', 100],
  ['created_at', 'date', 'src.' + slug(label) + '.created', 99],
  ['status', 'text', 'src.' + slug(label) + '.status', 86, 'new'],
];

export const RECORDS: Record<string, number> = {
  Plant: 4,
  'Production line': 23,
  Machine: 4120,
  Shift: 69,
  Operator: 1480,
  'Work order': 186340,
  Product: 3812,
  'Bill of materials': 3610,
  Material: 21400,
  Supplier: 940,
  'Purchase order': 58210,
  Warehouse: 11,
  'Stock level': 41800,
  Customer: 6210,
  'Sales region': 14,
  Quotation: 29750,
  'Sales order': 84212,
  'Price list': 38,
  Delivery: 80115,
  Shipment: 92400,
  Carrier: 27,
  Route: 310,
  Inspection: 142900,
  'Quality standard': 63,
  Defect: 9870,
  'Maintenance plan': 1210,
  'Spare part': 18300,
  Sensor: 12600,
  Invoice: 83990,
  'Cost centre': 212,
  Budget: 212,
  Employee: 2300,
  Certification: 4180,
  Training: 960,
  Specification: 2140,
  Test: 6900,
  'Engineering change': 1730,
  Site: 2,
  Line: 6,
  Article: 1290,
  Client: 1840,
  'Client order': 22600,
  Vendor: 410,
};

/** code, name, category, scope text. */
export const CATALOG: [string, string, string, string][] = [
  ['SAP', 'SAP ERP (S/4HANA, ECC)', 'ERP', 'OData / RFC · tables, CDS views'],
  ['SF', 'Salesforce', 'CRM', 'REST · objects and fields'],
  ['D365', 'Microsoft Dynamics 365', 'ERP / CRM', 'Dataverse · tables'],
  ['FAB', 'Microsoft Fabric · OneLake', 'data platform', 'Lakehouse, warehouse, Fabric IQ ontology'],
  ['DBX', 'Databricks', 'data platform', 'Unity Catalog · tables, Genie ontology'],
  ['SNW', 'Snowflake', 'data platform', 'information schema · semantic views'],
  ['SQL', 'SQL Server · Azure SQL', 'database', 'schema and row counts'],
  ['PG', 'PostgreSQL', 'database', 'schema and row counts'],
  ['ORA', 'Oracle', 'database', 'schema and row counts'],
  ['MES', 'Siemens Opcenter · MES', 'MES', 'plants, lines, assets, orders'],
  ['X3', 'Sage X3', 'ERP', 'facilities, items, business partners'],
  ['SN', 'ServiceNow', 'ITSM / CMMS', 'tables and CMDB'],
  ['WD', 'Workday', 'HRIS', 'workers, positions, organisations'],
  ['PI', 'AVEVA PI · OT', 'operations', 'tags and assets'],
  ['SP', 'SharePoint · files', 'documents', 'glossaries, procedures, specifications'],
];

/** Objects a connector discovers on verification, by catalogue code (reference line 1054). */
export const DISCOVER: Record<string, string[]> = {
  SAP: ['MARA (materials)', 'MAKT (descriptions)', 'KNA1 (customers)', 'LFA1 (vendors)', 'VBAK (sales orders)', 'EKKO (purchase orders)', 'MARC (plant data)', 'CSKS (cost centres)'],
  SF: ['Account', 'Contact', 'Opportunity', 'Quote', 'Pricebook2', 'Territory2'],
  MES: ['Plant', 'Line', 'Asset', 'Shift', 'WorkOrder', 'Downtime'],
  FAB: ['lakehouse.bronze.*', 'lakehouse.silver.customer', 'warehouse.dim_product', 'Fabric IQ · Northwind ontology'],
  DBX: ['main.sales.orders', 'main.supply.materials', 'Genie ontology · production'],
  SNW: ['SALES.ORDERS', 'SUPPLY.MATERIALS', 'semantic view · CUSTOMER_360'],
  X3: ['FACILITY', 'ITMMASTER', 'BPCUSTOMER', 'BPSUPPLIER', 'SORDER'],
  WD: ['Worker', 'Position', 'Organization', 'Certification'],
  SN: ['cmdb_ci', 'incident', 'change_request'],
  PI: ['AF elements', 'tags · 12,600'],
  SP: ['Glossary.docx', 'Procedures/', 'Specifications/'],
};
