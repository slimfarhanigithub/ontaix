/**
 * The keyboard and mouse hint. The shortcuts of reference/ontaix-studio-reference.html line 233,
 * without the story's `Space next` and `R restart`, without `S skip animation` (Skip animation
 * is a setting on the admin portal's Appearance page; S still toggles it) and without
 * `C coverage` (no cell has data behind it). Each shortcut is one unit that never breaks across
 * lines, so the hint wraps cleanly in the right-hand dock.
 */
import { useT, type MessageKey } from '../i18n/i18n';

/** Each shortcut: the key as shown (a letter stays as it is, a gesture is translated) and what it does. */
const SHORTCUTS: [string | MessageKey, MessageKey][] = [
  ['P', 'shell.hint.changes'],
  ['D', 'shell.hint.domains'],
  ['I', 'shell.hint.import'],
  ['A', 'shell.hint.arrange'],
  ['shell.hint.clickKey', 'shell.hint.newConcept'],
  ['shell.hint.dropKey', 'shell.hint.relate'],
  ['shell.hint.wheelKey', 'shell.hint.zoom'],
  ['F', 'shell.hint.fullScreen'],
];

export function Hint() {
  const t = useT();
  return (
    <ul className="hint" aria-label={t('shell.hint.label')}>
      {SHORTCUTS.map(([key, what]) => (
        <li key={key}>
          <kbd>{key.startsWith('shell.') ? t(key as MessageKey) : key}</kbd> {t(what)}
        </li>
      ))}
    </ul>
  );
}
