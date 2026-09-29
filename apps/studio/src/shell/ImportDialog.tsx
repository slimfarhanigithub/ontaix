/**
 * The import dialog: how the next chosen file is read, as `.chk` radio rows in `#imMode`, built
 * from the reference's `dialog()` and `.chk` markup (reference/ontaix-studio-reference.html line
 * 136 and lines 916-919). `Sentence by sentence` is the reference's path and the default;
 * `Ontology` maps an ontology or hierarchy file into a tree of proposals. The file picker, the
 * `I` key and drag and drop keep the reference's path.
 */
import { importDocument } from '../teach/teach';
import { importOntology } from '../teach/ontology';
import { store } from '../store/store';
import { refStyle } from './dom';

export type ImportMode = 'sentence' | 'ontology';

/** Every document type of the import and every ontology format. */
export const IMPORT_ACCEPT =
  '.txt,.md,.csv,.json,.docx,.pdf,.pptx,.xlsx,.html,.htm,.owl,.owx,.rdf,.xml,.ttl,.nt,.jsonld,.obo';

const MODES: { value: ImportMode; title: string; note: string }[] = [
  { value: 'sentence', title: 'Sentence by sentence', note: 'Each sentence is taught on its own' },
  {
    value: 'ontology',
    title: 'Ontology',
    note: 'OWL, SKOS, OBO, or a CSV or Excel hierarchy, mapped into a tree of proposals',
  },
];

/** The mode the next file chosen in the picker is read with; it returns to the default after. */
let nextMode: ImportMode = 'sentence';

/** Reads a chosen file with the mode picked in the dialog, then returns to the default. */
export function importChosenFile(file: File | null | undefined): void {
  const mode = nextMode;
  nextMode = 'sentence';
  if (mode === 'ontology') void importOntology(file);
  else void importDocument(file);
}

export function openImportDialog(picker: () => void): void {
  store.openDialog({
    title: 'Import',
    sub: 'a document or an existing ontology',
    body: (
      <div className="form">
        <div id="imMode" ref={refStyle('display:grid;gap:8px')}>
          {MODES.map((m) => (
            <label className="chk" key={m.value}>
              <input type="radio" name="imMode" value={m.value} defaultChecked={m.value === 'sentence'} />
              <span>
                <b>{m.title}</b>
                <small>{m.note}</small>
              </span>
            </label>
          ))}
        </div>
      </div>
    ),
    buttons: [
      { label: 'Cancel' },
      {
        label: 'Choose file',
        cls: 'primary',
        onClick: (bk) => {
          const chosen = bk.querySelector<HTMLInputElement>('input[name=imMode]:checked')?.value;
          nextMode = chosen === 'ontology' ? 'ontology' : 'sentence';
          picker();
        },
      },
    ],
  });
}
