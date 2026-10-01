/**
 * The keyboard and mouse hint. The shortcuts of reference/ontaix-studio-reference.html line 233,
 * without the story's `Space next` and `R restart` and without `S skip animation` (Skip animation
 * is a setting on the admin portal's Appearance page; S still toggles it). Each shortcut is one
 * unit that never breaks across lines, so the hint wraps cleanly in the right-hand dock.
 */
const SHORTCUTS: [string, string][] = [
  ['P', 'changes'],
  ['D', 'domains'],
  ['I', 'import · drop a file'],
  ['C', 'coverage'],
  ['A', 'arrange'],
  ['click', 'new concept'],
  ['drop on a cell', 'relate'],
  ['wheel', 'zoom'],
  ['F', 'full screen'],
];

export function Hint() {
  return (
    <ul className="hint" aria-label="Shortcuts">
      {SHORTCUTS.map(([key, what]) => (
        <li key={key}>
          <kbd>{key}</kbd> {what}
        </li>
      ))}
    </ul>
  );
}
