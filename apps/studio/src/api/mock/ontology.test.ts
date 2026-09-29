import { createEventBus } from '../events';
import type { ImportResult, OntologyImportResult, Proposal, Scene } from '../types';
import { createMockServer } from './server';

const enc = (t: string) => new TextEncoder().encode(t);
const file = (name: string, text: string | Uint8Array, type = 'application/octet-stream') => ({
  name,
  type,
  bytes: typeof text === 'string' ? enc(text) : text,
});

function body<T>(res: { status: number; body: unknown }, status = 200): T {
  expect(res.status, JSON.stringify(res.body)).toBe(status);
  return res.body as T;
}

function fresh() {
  const server = createMockServer(createEventBus());
  const co = body<Scene>(server.handle('GET', '/scene')).companies[0];
  return { server, co };
}

/** A ZIP archive of stored (uncompressed) members, enough for the mock's reader. */
function zip(parts: Record<string, string>): Uint8Array {
  const locals: number[] = [];
  const central: number[] = [];
  const u16 = (n: number) => [n & 0xff, (n >> 8) & 0xff];
  const u32 = (n: number) => [n & 0xff, (n >> 8) & 0xff, (n >> 16) & 0xff, (n >>> 24) & 0xff];
  let count = 0;
  for (const [name, text] of Object.entries(parts)) {
    const n = [...enc(name)];
    const data = [...enc(text)];
    const offset = locals.length;
    locals.push(...u32(0x04034b50), ...u16(20), ...u16(0), ...u16(0), ...u16(0), ...u16(0), ...u32(0), ...u32(data.length), ...u32(data.length), ...u16(n.length), ...u16(0), ...n, ...data);
    central.push(...u32(0x02014b50), ...u16(20), ...u16(20), ...u16(0), ...u16(0), ...u16(0), ...u16(0), ...u32(0), ...u32(data.length), ...u32(data.length), ...u16(n.length), ...u16(0), ...u16(0), ...u16(0), ...u16(0), ...u32(0), ...u32(offset), ...n);
    count++;
  }
  const end = [...u32(0x06054b50), ...u16(0), ...u16(0), ...u16(count), ...u16(count), ...u32(central.length), ...u32(locals.length), ...u16(0)];
  return new Uint8Array([...locals, ...central, ...end]);
}

const CT = 'http://schemas.openxmlformats.org/package/2006/content-types';
const REL = 'http://schemas.openxmlformats.org/package/2006/relationships';
const OFFICE = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships';
const types = (part: string, type: string) => `<Types xmlns="${CT}"><Override PartName="/${part}" ContentType="${type}"/></Types>`;
const rels = (targets: [string, string][]) =>
  `<Relationships xmlns="${REL}">${targets.map(([id, t]) => `<Relationship Id="${id}" Type="x" Target="${t}"/>`).join('')}</Relationships>`;

const deck = (mainType = 'application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml') =>
  zip({
    '[Content_Types].xml': types('ppt/presentation.xml', mainType),
    'ppt/presentation.xml': `<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="${OFFICE}"><p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst></p:presentation>`,
    'ppt/_rels/presentation.xml.rels': rels([['rId1', 'slides/slide1.xml']]),
    'ppt/slides/slide1.xml': `<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:p><a:r><a:t>A plant has many machines.</a:t></a:r></a:p></p:sld>`,
  });

describe('mock API: document types of the import', () => {
  it('reads a deck slide by slide and a workbook row by row', async () => {
    const { server } = fresh();
    const slides = body<ImportResult>(await server.importDocument(file('deck.pptx', deck())));
    expect(slides.sentences).toEqual(['A plant has many machines.']);
    expect(slides.positions).toEqual([{ unit: 'slide', index: 1 }]);

    const S = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';
    const book = zip({
      '[Content_Types].xml': types('xl/workbook.xml', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml'),
      'xl/workbook.xml': `<workbook xmlns="${S}" xmlns:r="${OFFICE}"><sheets><sheet name="A" sheetId="1" r:id="rId1"/></sheets></workbook>`,
      'xl/_rels/workbook.xml.rels': rels([['rId1', 'worksheets/sheet1.xml']]),
      'xl/sharedStrings.xml': `<sst xmlns="${S}"><si><t>Press 12</t></si><si><t>Line A</t></si></sst>`,
      'xl/worksheets/sheet1.xml': `<worksheet xmlns="${S}"><sheetData><row r="3"><c r="A3" t="s"><v>0</v></c><c r="B3" t="s"><v>1</v></c><c r="C3"><f>1+3</f><v>4</v></c></row></sheetData></worksheet>`,
    });
    const rows = body<ImportResult>(await server.importDocument(file('plant.xlsx', book)));
    expect(rows.sentences).toEqual(['Press 12, Line A, 4']);
    expect(rows.positions).toEqual([{ unit: 'sheet', index: 1, row: 3 }]);
  });

  it('reads a web page without its scripts and embedded content', async () => {
    const { server } = fresh();
    const page = '<!doctype html><html><body><h1>Operations overview</h1><script>alert(1)</script><p>A plant has many machines.</p><iframe>Hidden frame text here</iframe></body></html>';
    const read = body<ImportResult>(await server.importDocument(file('page.html', page)));
    expect(read.sentences).toEqual(['Operations overview', 'A plant has many machines.']);
  });

  it('refuses macro-enabled, legacy and disagreeing files with 415', async () => {
    const { server } = fresh();
    for (const f of [
      file('deck.pptx', deck('application/vnd.ms-powerpoint.presentation.macroEnabled.main+xml')),
      file('old.docx', new Uint8Array([0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1, 0, 0])),
      file('deck.docx', deck()),
      file('page.txt', '<html><body><p>A plant has many machines.</p></body></html>'),
    ])
      expect((await server.importDocument(f)).status).toBe(415);
  });
});

describe('mock API: ontology import', () => {
  it('maps a CSV hierarchy and proposes it once with origin ontology_import', async () => {
    const { server, co } = fresh();
    const csv = 'label,parent,action\nOperations,,\nMaintenance,Operations,runs\nWork Order,Maintenance,is a\nOrphan,Nowhere,\n';
    const mapped = body<OntologyImportResult>(await server.importOntology(file('tree.csv', csv), { companyId: co.id }));
    expect(mapped.format).toBe('csv');
    expect(mapped.drafts.map((d) => (d.type === 'concept' ? [d.label, d.action] : null))).toEqual([
      ['Operations', 'includes'],
      ['Maintenance', 'runs'],
      ['Work Order', 'includes'],
    ]);
    expect(mapped.notes.map((n) => n.requires)).toEqual([[], [0], [1]]);
    expect(mapped.skipped).toEqual([
      { source: 'row 5', reason: 'unknown_parent' },
      { source: 'row 4', label: 'Work Order', reason: 'forbidden_action' },
    ]);
    expect(server.handle('POST', `/ontology-imports/${mapped.ontologyImportId}/proposals`, { indexes: [1] }).status).toBe(422);
    const made = body<Proposal[]>(server.handle('POST', `/ontology-imports/${mapped.ontologyImportId}/proposals`, { indexes: [0, 1, 2] }), 202);
    expect(made.map((p) => p.origin)).toEqual(['ontology_import', 'ontology_import', 'ontology_import']);
    expect(made[0].why).toBe('Imported from tree.csv · row 2');
    const again = server.handle('POST', `/ontology-imports/${mapped.ontologyImportId}/proposals`, { indexes: [0, 1, 2] });
    expect((again.body as { code: string }).code).toBe('ontology_import_submitted');
    expect(body<OntologyImportResult>(server.handle('GET', `/ontology-imports/${mapped.ontologyImportId}`)).drafts).toHaveLength(3);
  });

  it('maps OBO terms and RDF/XML classes with parents, relations and reuse', async () => {
    const { server, co } = fresh();
    const obo = 'format-version: 1.2\n\n[Term]\nid: PL:1\nname: equipment\n\n[Term]\nid: PL:2\nname: heat exchanger\nis_a: PL:1 ! equipment\nrelationship: part_of PL:1\n\n[Typedef]\nid: part_of\nname: part of\n';
    const terms = body<OntologyImportResult>(await server.importOntology(file('plant.obo', obo), { companyId: co.id }));
    expect(terms.drafts.map((d) => d.type)).toEqual(['concept', 'spec', 'relation']);
    expect(terms.drafts[2]).toMatchObject({ aLabel: 'Heat exchanger', bLabel: 'Equipment', action: 'part of' });

    const rdf = `<?xml version="1.0"?><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#" xmlns:owl="http://www.w3.org/2002/07/owl#">
      <owl:Class rdf:about="http://x/${co.name.replace(/\W/g, '')}"><rdfs:label>${co.name}</rdfs:label></owl:Class>
      <owl:Class rdf:about="http://x/Pump"><rdfs:label xml:lang="fr">Pompe</rdfs:label><rdfs:label xml:lang="en">Pump</rdfs:label><rdfs:subClassOf rdf:resource="http://x/${co.name.replace(/\W/g, '')}"/></owl:Class>
    </rdf:RDF>`;
    const classes = body<OntologyImportResult>(await server.importOntology(file('plant.rdf', rdf), { companyId: co.id, languages: 'fr-CA,en' }));
    expect(classes.skipped).toContainEqual(expect.objectContaining({ label: co.name, reason: 'reused_existing' }));
    expect(classes.drafts).toEqual([
      expect.objectContaining({ type: 'spec', label: 'Pompe', parentId: co.rootId }),
    ]);
    expect(classes.notes[0].labelLanguage).toBe('fr');
  });

  it('refuses DTDs, remote contexts, the importDocs switch and formats the mock does not read', async () => {
    const { server, co } = fresh();
    const code = async (name: string, text: string) => (await server.importOntology(file(name, text), { companyId: co.id })).status;
    expect(await code('x.rdf', '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "b">]><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"/>')).toBe(415);
    expect(await code('x.jsonld', '{"@context": "https://schema.org/", "@id": "http://x/a"}')).toBe(422);
    expect(await code('x.ttl', '@prefix : <http://x/> .')).toBe(415);
    server.handle('PATCH', '/settings', { importDocs: false });
    expect(await code('x.csv', 'label,parent\nA thing,\n')).toBe(409);
  });
});
