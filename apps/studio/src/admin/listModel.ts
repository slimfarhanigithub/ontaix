/**
 * The searchable, filterable, sortable, paginated list model behind every admin list (the
 * reference's `renderList`, line 921). Pure: rows in, one visible page out.
 */

export type Row = Record<string, unknown>;

export interface ListQuery {
  /** Search text as typed; trimmed and lower-cased before matching. */
  q: string;
  /** Selected filter value, or null for `All`. */
  filter: string | null;
  sortKey: string | null;
  /** 1 ascending, -1 descending. */
  sortDir: 1 | -1;
  /** Zero-based page index; clamped to the pages that exist. */
  page: number;
}

export interface ListSpec {
  searchKeys: string[];
  filterKey?: string;
  pageSize: number;
}

export interface ListView<R extends Row> {
  /** Every row matching the search and the filter, sorted. */
  matching: R[];
  /** The rows of the current page. */
  items: R[];
  page: number;
  pages: number;
}

export const EMPTY_QUERY: ListQuery = { q: '', filter: null, sortKey: null, sortDir: 1, page: 0 };

/** Distinct values of the filter key, sorted; the pills show only when there are two or more. */
export function filterValues<R extends Row>(rows: R[], filterKey: string | undefined): string[] {
  if (!filterKey) return [];
  return [...new Set(rows.map((r) => r[filterKey] as string))].sort();
}

/** Applies search, filter, sort and paging, the way the reference's `draw` does. */
export function viewList<R extends Row>(rows: R[], spec: ListSpec, query: ListQuery): ListView<R> {
  const q = query.q.trim().toLowerCase();
  let list = rows.filter(
    (r) =>
      (!query.filter || (spec.filterKey !== undefined && r[spec.filterKey] === query.filter)) &&
      (!q || spec.searchKeys.some((k) => String(r[k]).toLowerCase().includes(q))),
  );
  const key = query.sortKey;
  if (key) {
    list = list.slice().sort((a, b) => {
      const x = a[key] as string | number,
        y = b[key] as string | number;
      return (x > y ? 1 : x < y ? -1 : 0) * query.sortDir;
    });
  }
  const pages = Math.max(1, Math.ceil(list.length / spec.pageSize));
  const page = Math.min(Math.max(query.page, 0), pages - 1);
  return { matching: list, items: list.slice(page * spec.pageSize, (page + 1) * spec.pageSize), page, pages };
}

/** A header click: the same column flips the direction, another column sorts ascending. */
export function toggleSort(query: ListQuery, key: string | undefined): ListQuery {
  if (!key) return query;
  if (query.sortKey === key) return { ...query, sortDir: query.sortDir === 1 ? -1 : 1 };
  return { ...query, sortKey: key, sortDir: 1 };
}

/** Counts in en-GB, the reference's `toLocaleString('en-GB')`. */
export const en = (n: number): string => n.toLocaleString('en-GB');

/** `N of M`, the start of every list footer. */
export const countText = (shown: number, total: number, footer: string | null): string =>
  `${en(shown)} of ${en(total)}${footer !== null ? ' · ' + footer : ''}`;
