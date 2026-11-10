/**
 * Message interpolation: `{name}` takes the parameter's value, and
 * `{n, plural, one {proposal} other {proposals}}` picks the branch the locale's plural rule gives
 * the number (an exact `=0 {none}` branch wins first), with `#` inside a branch standing for the
 * number. No other syntax; a template with no braces is returned as it is.
 */

export type Params = Record<string, string | number>;

const pluralRules = new Map<string, Intl.PluralRules>();

function rulesFor(locale: string): Intl.PluralRules {
  let rules = pluralRules.get(locale);
  if (!rules) {
    rules = new Intl.PluralRules(locale);
    pluralRules.set(locale, rules);
  }
  return rules;
}

/** The index of the `}` closing the `{` at `open`, braces inside counted; -1 when unbalanced. */
function closing(s: string, open: number): number {
  let depth = 0;
  for (let i = open; i < s.length; i++) {
    if (s[i] === '{') depth++;
    else if (s[i] === '}' && --depth === 0) return i;
  }
  return -1;
}

/** The `selector {text}` branches of a plural argument, in order. */
function branches(spec: string): [string, string][] {
  const out: [string, string][] = [];
  let i = 0;
  while (i < spec.length) {
    const open = spec.indexOf('{', i);
    if (open < 0) break;
    const end = closing(spec, open);
    if (end < 0) break;
    out.push([spec.slice(i, open).trim(), spec.slice(open + 1, end)]);
    i = end + 1;
  }
  return out;
}

function pluralBranch(spec: string, n: number, locale: string): string {
  const all = branches(spec);
  const exact = all.find(([sel]) => sel === `=${n}`);
  if (exact) return exact[1];
  const category = rulesFor(locale).select(n);
  const byCategory = all.find(([sel]) => sel === category);
  if (byCategory) return byCategory[1];
  return all.find(([sel]) => sel === 'other')?.[1] ?? '';
}

/** `template` with its parameters filled in for `locale`. A parameter left out stays as `{name}`. */
export function formatMessage(template: string, params: Params | undefined, locale: string, count?: number): string {
  if (!template.includes('{') && count === undefined) return template;
  let out = '';
  let i = 0;
  while (i < template.length) {
    const ch = template[i];
    if (ch === '#' && count !== undefined) {
      out += String(count);
      i++;
      continue;
    }
    if (ch !== '{') {
      out += ch;
      i++;
      continue;
    }
    const end = closing(template, i);
    if (end < 0) {
      out += template.slice(i);
      break;
    }
    const inner = template.slice(i + 1, end);
    const comma = inner.indexOf(',');
    if (comma < 0) {
      const name = inner.trim();
      const value = params?.[name];
      out += value === undefined ? `{${name}}` : String(value);
    } else {
      const name = inner.slice(0, comma).trim();
      const rest = inner.slice(comma + 1);
      const kind = rest.slice(0, rest.indexOf(',')).trim();
      const value = params?.[name];
      if (kind === 'plural' && typeof value === 'number') {
        const spec = rest.slice(rest.indexOf(',') + 1);
        out += formatMessage(pluralBranch(spec, value, locale), params, locale, value);
      } else {
        out += value === undefined ? `{${name}}` : String(value);
      }
    }
    i = end + 1;
  }
  return out;
}

/** The parameter names a template uses, plural arguments included; what a translation must keep. */
export function paramNames(template: string): string[] {
  const names = new Set<string>();
  let i = 0;
  while (i < template.length) {
    const open = template.indexOf('{', i);
    if (open < 0) break;
    const end = closing(template, open);
    if (end < 0) break;
    const inner = template.slice(open + 1, end);
    const comma = inner.indexOf(',');
    names.add((comma < 0 ? inner : inner.slice(0, comma)).trim());
    if (comma >= 0) {
      const spec = inner.slice(inner.indexOf(',', comma + 1) + 1);
      for (const [, text] of branches(spec)) for (const name of paramNames(text)) names.add(name);
    }
    i = end + 1;
  }
  return [...names].sort();
}
