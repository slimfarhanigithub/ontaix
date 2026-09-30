/**
 * The ways an imported file can be read: as a document, whole or sentence by sentence, or as an
 * ontology in one of the formats ontology import reads. Detection picks one; the owner may
 * choose any other in the `#imAs` dialog.
 */
import type { ImportDetection, OntologyFormat } from '../api/types';

export type ImportReading = 'whole' | 'sentences' | OntologyFormat;

export interface LastImport {
  file: File;
  detection: ImportDetection;
  reading: ImportReading;
}

/** Every reading, in the order the `#imAs` dialog lists them, with its label. */
export const READINGS: { reading: ImportReading; label: string }[] = [
  { reading: 'whole', label: 'Document (whole)' },
  { reading: 'sentences', label: 'Document (sentences)' },
  { reading: 'turtle', label: 'Ontology (Turtle)' },
  { reading: 'rdf_xml', label: 'Ontology (RDF/XML)' },
  { reading: 'json_ld', label: 'Ontology (JSON-LD)' },
  { reading: 'owl_xml', label: 'Ontology (OWL/XML)' },
  { reading: 'n_triples', label: 'Ontology (N-Triples)' },
  { reading: 'obo', label: 'Ontology (OBO)' },
  { reading: 'csv', label: 'Ontology (CSV)' },
  { reading: 'xlsx', label: 'Ontology (XLSX)' },
];

export const readingLabel = (reading: ImportReading): string => READINGS.find((r) => r.reading === reading)?.label ?? reading;

/** The reading detection picks: the detected ontology format, else the whole document. */
export const detectedReading = (d: ImportDetection): ImportReading => (d.kind === 'ontology' && d.format ? d.format : 'whole');
