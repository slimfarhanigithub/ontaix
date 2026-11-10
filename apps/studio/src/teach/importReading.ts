/**
 * The ways an imported file can be read: as a document, whole or sentence by sentence, or as an
 * ontology in one of the formats ontology import reads. Detection picks one; the owner may
 * choose any other in the `#imAs` dialog.
 */
import type { ImportDetection, OntologyFormat } from '../api/types';
import { t, type MessageKey } from '../i18n/i18n';

export type ImportReading = 'whole' | 'sentences' | OntologyFormat;

export interface LastImport {
  file: File;
  detection: ImportDetection;
  reading: ImportReading;
}

/** A reading whose label is read in the portal language of the moment. */
const named = (reading: ImportReading, key: MessageKey): { reading: ImportReading; label: string } => ({
  reading,
  get label(): string {
    return t(key);
  },
});

/** Every reading, in the order the `#imAs` dialog lists them, with its label. */
export const READINGS: { reading: ImportReading; label: string }[] = [
  named('whole', 'teach.reading.whole'),
  named('sentences', 'teach.reading.sentences'),
  named('turtle', 'teach.reading.turtle'),
  named('rdf_xml', 'teach.reading.rdfXml'),
  named('json_ld', 'teach.reading.jsonLd'),
  named('owl_xml', 'teach.reading.owlXml'),
  named('n_triples', 'teach.reading.nTriples'),
  named('obo', 'teach.reading.obo'),
  named('csv', 'teach.reading.csv'),
  named('xlsx', 'teach.reading.xlsx'),
];

export const readingLabel = (reading: ImportReading): string => READINGS.find((r) => r.reading === reading)?.label ?? reading;

/** The reading detection picks: the detected ontology format, else the whole document. */
export const detectedReading = (d: ImportDetection): ImportReading => (d.kind === 'ontology' && d.format ? d.format : 'whole');
