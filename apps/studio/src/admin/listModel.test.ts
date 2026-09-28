import { isDisableConfirmed } from './confirmText';
import { countText, EMPTY_QUERY, filterValues, toggleSort, viewList, type ListQuery } from './listModel';

interface R extends Record<string, unknown> {
  id: number;
  name: string;
  dept: string;
  n: number;
}

const rows: R[] = Array.from({ length: 95 }, (_, i) => ({
  id: i,
  name: `User ${String(i).padStart(2, '0')}`,
  dept: ['Sales', 'IT', 'Quality'][i % 3],
  n: (i * 37) % 11,
}));
const spec = { searchKeys: ['name', 'dept'], filterKey: 'dept', pageSize: 40 };
const q = (patch: Partial<ListQuery>): ListQuery => ({ ...EMPTY_QUERY, ...patch });

describe('admin list model', () => {
  it('pages rows 40 at a time and clamps the page into range', () => {
    const first = viewList(rows, spec, EMPTY_QUERY);
    expect(first.pages).toBe(3);
    expect(first.items).toHaveLength(40);
    expect(first.items[0].id).toBe(0);
    const last = viewList(rows, spec, q({ page: 2 }));
    expect(last.items.map((r) => r.id)).toEqual(Array.from({ length: 15 }, (_, i) => 80 + i));
    expect(viewList(rows, spec, q({ page: 9 })).page).toBe(2);
    expect(viewList(rows, spec, q({ page: -3 })).page).toBe(0);
    expect(viewList([], spec, EMPTY_QUERY)).toMatchObject({ items: [], page: 0, pages: 1 });
  });

  it('searches every search key, trimmed and case-insensitive', () => {
    const v = viewList(rows, spec, q({ q: '  user 1 ' }));
    expect(v.matching.map((r) => r.id)).toEqual([10, 11, 12, 13, 14, 15, 16, 17, 18, 19]);
    expect(viewList(rows, spec, q({ q: 'QUALITY' })).matching).toHaveLength(31);
    expect(viewList(rows, spec, q({ q: 'nobody' })).items).toEqual([]);
  });

  it('filters on the filter key and combines with search', () => {
    expect(viewList(rows, spec, q({ filter: 'IT' })).matching.every((r) => r.dept === 'IT')).toBe(true);
    const both = viewList(rows, spec, q({ filter: 'Sales', q: 'user 0' }));
    expect(both.matching.map((r) => r.id)).toEqual([0, 3, 6, 9]);
  });

  it('lists distinct filter values sorted, and none without a filter key', () => {
    expect(filterValues(rows, 'dept')).toEqual(['IT', 'Quality', 'Sales']);
    expect(filterValues(rows, undefined)).toEqual([]);
  });

  it('sorts ascending on first click and flips on the second, keeping ties stable', () => {
    let query = toggleSort(EMPTY_QUERY, 'n');
    expect(query).toMatchObject({ sortKey: 'n', sortDir: 1 });
    const asc = viewList(rows, spec, query).matching;
    expect(asc[0].n).toBe(0);
    expect(asc.map((r) => r.n)).toEqual([...rows.map((r) => r.n)].sort((a, b) => a - b));
    const zeros = asc.filter((r) => r.n === 0).map((r) => r.id);
    expect(zeros).toEqual([...zeros].sort((a, b) => a - b));
    query = toggleSort(query, 'n');
    expect(query.sortDir).toBe(-1);
    expect(viewList(rows, spec, query).matching[0].n).toBe(10);
    expect(toggleSort(query, 'name')).toMatchObject({ sortKey: 'name', sortDir: 1 });
    expect(toggleSort(query, undefined)).toBe(query);
  });

  it('writes the footer count in en-GB with the page footer text', () => {
    expect(countText(1234, 2400, '12 with access')).toBe('1,234 of 2,400 · 12 with access');
    expect(countText(0, 0, null)).toBe('0 of 0');
    expect(countText(3, 3, '')).toBe('3 of 3 · ');
  });
});

describe('typed disable confirmation', () => {
  it('accepts disable in any case with surrounding spaces', () => {
    expect(isDisableConfirmed('disable')).toBe(true);
    expect(isDisableConfirmed('  DISABLE ')).toBe(true);
    expect(isDisableConfirmed('Disable')).toBe(true);
  });

  it('refuses anything else', () => {
    for (const typed of ['', 'disabl', 'disabled', 'dis able', 'yes', 'disable!', 'enable']) expect(isDisableConfirmed(typed)).toBe(false);
  });
});
