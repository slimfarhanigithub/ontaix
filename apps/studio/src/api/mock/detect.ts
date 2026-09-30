/**
 * Import detection of the in-browser mock, mirroring `POST /import/detect`: the bytes decide
 * when they are unambiguous (PDF, Word, PowerPoint and HTML are documents; an RDF/XML or
 * OWL/XML root, JSON naming `@context` or `@graph`, an OBO header with terms, a Turtle
 * directive or lines of full N-Triples are ontologies; a CSV or XLSX table is an ontology when
 * its header row is a hierarchy header), and text with no ontology signal follows its extension,
 * else its declared media type.
 */
import type * as T from '../types';
import { checkedFileName, ExtractRefusal, IMPORT_MAX_BYTES, sniff, xlsxHeader } from './extract';

const ONTOLOGY_MAX_BYTES = 20 * 1024 * 1024;
const XLSX: T.ImportMediaType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
const TEXT_BY_EXTENSION: Record<string, T.ImportMediaType> = {
  txt: 'text/plain',
  md: 'text/markdown',
  markdown: 'text/markdown',
  csv: 'text/csv',
  json: 'application/json',
};
const DOCUMENT_EXTENSIONS = new Set([...Object.keys(TEXT_BY_EXTENSION), 'text', 'docx', 'pdf', 'pptx', 'xlsx', 'html', 'htm']);
const TEXT_TYPES = new Set<string>(Object.values(TEXT_BY_EXTENSION));
const FORMAT_BY_EXTENSION: Record<string, T.OntologyFormat> = {
  rdf: 'rdf_xml',
  xml: 'rdf_xml',
  owl: 'rdf_xml',
  owx: 'owl_xml',
  ttl: 'turtle',
  jsonld: 'json_ld',
  nt: 'n_triples',
  obo: 'obo',
};
const FORMAT_BY_MEDIA_TYPE: Record<string, T.OntologyFormat> = {
  'application/rdf+xml': 'rdf_xml',
  'application/owl+xml': 'owl_xml',
  'text/turtle': 'turtle',
  'application/ld+json': 'json_ld',
  'application/n-triples': 'n_triples',
};
const TURTLE_DIRECTIVE = /^\s*(?:@prefix|@base|PREFIX|BASE)\s+\S*\s*</m;
const N_TRIPLE = /^(<[^>\s]*>|_:\S+)\s+<[^>\s]*>\s+(<[^>\s]*>|_:\S+|"(?:[^"\\]|\\.)*"(\^\^<[^>\s]*>|@[A-Za-z0-9-]+)?)\s*\.\s*(#.*)?$/;
const LEVEL = /^level\s*\d+$/;

export async function detectImport(file: { name: string; type: string; bytes: Uint8Array }): Promise<T.ImportDetection> {
  const fileName = checkedFileName(file.name);
  if (file.bytes.length > Math.max(IMPORT_MAX_BYTES, ONTOLOGY_MAX_BYTES))
    throw new ExtractRefusal(413, 'payload_too_large', 'the file is larger than either import reads');
  const sniffed = await sniff(file.bytes);
  if (sniffed === 'refused') throw new ExtractRefusal(415, 'unsupported_media_type', 'the file is neither a document nor an ontology the import reads');
  if (sniffed === XLSX)
    return isHierarchy(await xlsxHeader(file.bytes))
      ? { kind: 'ontology', format: 'xlsx', mediaType: XLSX }
      : { kind: 'document', format: null, mediaType: XLSX };
  if (sniffed !== 'text') return { kind: 'document', format: null, mediaType: sniffed };
  const ext = fileName.includes('.') ? fileName.split('.').pop()!.toLowerCase() : '';
  const declared = file.type.split(';')[0].trim().toLowerCase();
  const mediaType: T.ImportMediaType =
    TEXT_BY_EXTENSION[ext] || (!DOCUMENT_EXTENSIONS.has(ext) && TEXT_TYPES.has(declared) ? (declared as T.ImportMediaType) : 'text/plain');
  const text = new TextDecoder('utf-8').decode(file.bytes).replace(/^﻿/, '');
  let format = contentFormat(text);
  if (!format && mediaType === 'text/csv' && isHierarchy(csvHeader(text))) format = 'csv';
  if (!format && !DOCUMENT_EXTENSIONS.has(ext)) format = FORMAT_BY_EXTENSION[ext] || FORMAT_BY_MEDIA_TYPE[declared] || null;
  return format ? { kind: 'ontology', format, mediaType } : { kind: 'document', format: null, mediaType };
}

/** The ontology format the text shows with no declaration, or null. */
function contentFormat(text: string): T.OntologyFormat | null {
  const head = text.trimStart();
  if (head.startsWith('<')) {
    const root = /<(?!\?|!)([\w.-]+:)?([\w.-]+)[\s>/]/.exec(head);
    if (root && root[2] === 'RDF') return 'rdf_xml';
    if (root && root[2] === 'Ontology') return 'owl_xml';
  }
  if (head.startsWith('{') || head.startsWith('[')) return /"@(?:context|graph)"\s*:/.test(text) ? 'json_ld' : null;
  const lines = text.split(/\r?\n/).map((l) => l.trim());
  if (lines.slice(0, 50).some((l) => l.startsWith('format-version:')) && lines.includes('[Term]')) return 'obo';
  if (TURTLE_DIRECTIVE.test(text.slice(0, 65536))) return 'turtle';
  const statements = lines.filter((l) => l && !l.startsWith('#'));
  if (statements.length && statements.slice(0, 1000).every((l) => N_TRIPLE.test(l))) return 'n_triples';
  return null;
}

/** The cells of the first non-empty CSV line, split on commas, semicolons or tabs. */
function csvHeader(text: string): string[] {
  const line = text.split(/\r?\n/).find((l) => l.trim()) || '';
  return line.split(/[,;\t]/).map((c) => c.trim().replace(/^"|"$/g, ''));
}

/** Label and parent columns, or at least one `Level <n>` column. */
function isHierarchy(cells: string[]): boolean {
  const names = new Set(cells.map((c) => c.trim().toLowerCase()));
  return (names.has('label') && names.has('parent')) || [...names].some((n) => LEVEL.test(n));
}
