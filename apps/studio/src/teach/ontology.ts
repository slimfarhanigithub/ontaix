/**
 * Ontology import: an OWL, SKOS or OBO file, or a CSV or Excel hierarchy, is mapped by the API
 * into a tree of drafts for the taught company and proposed whole; the tree is then reviewed in
 * the changes panel like any other proposals. Label languages come from the browser's language
 * list, individuals are skipped and the tree goes under the company's root. Progress and outcome
 * use the existing caption; a refusal is the reference's toast.
 */
import { api } from '../api/client';
import { ApiError, type OntologyFormat } from '../api/types';
import { store } from '../store/store';
import { beginProcessing } from './processing';

/** At most this many label languages go to the API, first preferred. */
const MAX_LANGUAGES = 10;
const LANGUAGE_TAG = /^[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*$/;

/** The browser's language preference as BCP 47 tags, first preferred, `en` when it names none. */
export function browserLanguages(list: readonly string[] = navigator.languages || [navigator.language]): string {
  const tags: string[] = [];
  for (const tag of list) {
    if (LANGUAGE_TAG.test(tag) && !tags.some((t) => t.toLowerCase() === tag.toLowerCase())) tags.push(tag);
    if (tags.length === MAX_LANGUAGES) break;
  }
  return (tags.length ? tags : ['en']).join(',');
}

/** Maps a file into the taught company and proposes every draft of the tree; `format`, when
 * given, is the format the file is read as, in place of its extension. */
export async function importOntology(file: File | null | undefined, format?: OntologyFormat): Promise<void> {
  const company = store.s.activeCompany;
  if (!file || store.ui.importing || !company?.sid) return;
  store.ui.importing = true;
  const end = beginProcessing();
  const kicker = `Mapping ${file.name}`;
  try {
    store.caption(kicker, '');
    const mapped = await api.importOntology(file, {
      companyId: company.sid,
      languages: browserLanguages(),
      individuals: 'skip',
      ...(format ? { format } : {}),
    });
    const indexes = mapped.drafts.map((_, i) => i);
    const created = indexes.length ? await api.proposeOntologyImport(mapped.ontologyImportId, indexes) : [];
    await store.refreshProposals();
    store.caption(kicker, `${created.length} proposals from ${file.name} · ${mapped.skipped.length} skipped`);
  } catch (err) {
    if (!(err instanceof ApiError)) throw err;
    store.refused(err);
  } finally {
    store.ui.importing = false;
    end();
  }
}
