/**
 * Import routing: a picked or dropped file is sent to `POST /import/detect`, which says from its
 * bytes whether it is a document or an ontology. A document is read whole; an ontology goes to
 * ontology import in the detected format. The file, its detection and its reading are kept, so
 * `#imAs` can import the same file again read another way.
 */
import { api } from '../api/client';
import { ApiError } from '../api/types';
import { store } from '../store/store';
import { detectedReading, type ImportReading } from './importReading';
import { importOntology } from './ontology';
import { importDocument } from './teach';

/** Detects what the file is, then imports it read that way. */
export async function importFile(file: File | null | undefined): Promise<void> {
  if (!file || store.ui.importing) return;
  store.ui.importing = true;
  store.bump();
  let detection;
  try {
    detection = await api.detectImport(file);
  } catch (err) {
    const reason = err instanceof ApiError ? err.problem.detail || err.problem.title : (err as Error).message;
    store.caption('Import failed', `${file.name} could not be read (${reason}).`);
    return;
  } finally {
    store.ui.importing = false;
    store.bump();
  }
  const reading = detectedReading(detection);
  store.ui.lastImport = { file, detection, reading };
  store.bump();
  await readFile(reading);
}

/** Imports the last imported file again, read the way the owner chose. */
export async function importAgain(reading: ImportReading): Promise<void> {
  const last = store.ui.lastImport;
  if (!last || store.ui.importing) return;
  store.ui.lastImport = { ...last, reading };
  store.bump();
  await readFile(reading);
}

async function readFile(reading: ImportReading): Promise<void> {
  const last = store.ui.lastImport;
  if (!last) return;
  if (reading === 'whole' || reading === 'sentences')
    return importDocument(last.file, reading === 'whole' ? 'document' : 'sentences', last.detection.mediaType);
  return importOntology(last.file, reading);
}
