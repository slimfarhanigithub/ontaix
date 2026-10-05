/**
 * Only src/design holds raw colours. Every other stylesheet, module and component styles through
 * the tokens, so one theme switch and one rebrand reach everything. Files still carrying raw
 * colours from before the design system are listed in RESTYLE_PENDING until their restyle lands;
 * a listed file that no longer holds any fails the build until its row is removed.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, resolve, sep } from 'node:path';

const SRC = resolve(__dirname, '..');

/** Files allowed to hold raw colours for now, relative to src, with the pull request that drains them. */
const RESTYLE_PENDING: Record<string, string> = {
  'styles/reference.css': 'shell restyle',
  'styles/studio.css': 'shell restyle',
  'admin/pages/ModelPages.tsx': 'shell restyle',
  'admin/pages/PortalPages.tsx': 'shell restyle',
  'admin/SourceWizard.tsx': 'shell restyle',
  'platform/PlatformAudit.tsx': 'shell restyle',
  'shell/Drawer.tsx': 'shell restyle',
  'shell/Legend.tsx': 'canvas restyle',
  'canvas/cells.ts': 'canvas restyle',
  'canvas/constants.ts': 'canvas restyle',
  'canvas/neck.ts': 'canvas restyle',
  'canvas/regions.ts': 'canvas restyle',
  'canvas/themes.ts': 'canvas restyle',
};

/** `#rgb`, `#rrggbb`, `#rrggbbaa`, and `rgb()`, `rgba()`, `hsl()` or `hsla()` with literal channels, outside a word. */
const RAW_COLOUR = /(?<![\w-])#(?:[0-9a-f]{8}|[0-9a-f]{6}|[0-9a-f]{3,4})(?![\w-])|(?<![\w-])(?:rgba?|hsla?)\(\s*\d/gi;

/** Modules outside the design folder whose colours are data, not styling: the in-browser mock's fixtures and tests. */
const skip = (rel: string): boolean =>
  rel.startsWith('design/') || rel.startsWith('api/mock/') || /\.test\.tsx?$/.test(rel) || rel === 'test-setup.ts';

function* walk(dir: string): Generator<string> {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) yield* walk(full);
    else if (/\.(css|ts|tsx)$/.test(name)) yield full;
  }
}

const files = [...walk(SRC)].map((f) => relative(SRC, f).split(sep).join('/')).filter((rel) => !skip(rel));

describe('raw colours live in src/design only', () => {
  it.each(files.filter((rel) => !(rel in RESTYLE_PENDING)))('%s', (rel) => {
    const hits = [...readFileSync(join(SRC, rel), 'utf8').matchAll(RAW_COLOUR)].map((m) => m[0]);
    expect(hits, `${rel} styles with raw colours; use a token`).toEqual([]);
  });

  it('every RESTYLE_PENDING file still holds a raw colour', () => {
    const drained = Object.keys(RESTYLE_PENDING).filter((rel) => readFileSync(join(SRC, rel), 'utf8').search(RAW_COLOUR) === -1);
    expect(drained, 'remove these rows from RESTYLE_PENDING').toEqual([]);
  });
});
