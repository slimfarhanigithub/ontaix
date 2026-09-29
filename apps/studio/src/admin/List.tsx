/**
 * The admin list: search box, filter pills, sortable sticky header, footer count and paging.
 * Markup from `renderList` in reference/ontaix-studio-reference.html line 921; the model is
 * ./listModel.
 */
import { useState, type CSSProperties, type ReactNode } from 'react';

import { countText, EMPTY_QUERY, filterValues, toggleSort, viewList, type ListQuery, type Row } from './listModel';

export interface Column {
  label: string;
  key?: string;
  num?: boolean;
  w?: string;
}

export interface ListProps<R extends Row> {
  columns: Column[];
  rows: R[];
  rowKey: (r: R) => string | number;
  searchKeys: string[];
  filterKey?: string;
  pageSize?: number;
  /** The cells of one row. */
  renderRow: (r: R) => ReactNode;
  footer?: (list: R[]) => string;
  height?: string;
}

const thStyle = (c: Column): CSSProperties => ({
  cursor: 'pointer',
  ...(c.num ? { textAlign: 'right' } : {}),
  ...(c.w ? { width: c.w } : {}),
});

export function List<R extends Row>({ columns, rows, rowKey, searchKeys, filterKey, pageSize = 50, renderRow, footer, height }: ListProps<R>) {
  const [query, setQuery] = useState<ListQuery>(EMPTY_QUERY);

  const view = viewList(rows, { searchKeys, filterKey, pageSize }, query);
  const filters = filterValues(rows, filterKey);
  return (
    <>
      <div className="lst-top">
        <input
          className="search"
          placeholder="Search…"
          value={query.q}
          onChange={(e) => setQuery({ ...query, q: e.target.value, page: 0 })}
        />
        <div className="filters">
          {filters.length > 1
            ? [
                <button key="" data-f="" className={query.filter === null ? 'on' : undefined} onClick={() => setQuery({ ...query, filter: null, page: 0 })}>
                  All
                </button>,
                ...filters.map((f) => (
                  <button key={f} data-f={f} className={query.filter === f ? 'on' : undefined} onClick={() => setQuery({ ...query, filter: f, page: 0 })}>
                    {f}
                  </button>
                )),
              ]
            : null}
        </div>
      </div>
      <div className="lst-wrap" style={height ? { maxHeight: height } : undefined}>
        <table className="tbl">
          <thead>
            <tr>
              {columns.map((c, i) => (
                <th key={i} data-i={i} style={thStyle(c)} onClick={() => setQuery(toggleSort(query, c.key))}>
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {view.items.length ? (
              view.items.map((r) => <tr key={rowKey(r)}>{renderRow(r)}</tr>)
            ) : (
              <tr>
                <td colSpan={columns.length} style={{ color: 'var(--ink-3)' }}>
                  Nothing matches.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="lst-foot">
        <span className="count">{countText(view.matching.length, rows.length, footer ? footer(view.matching) : null)}</span>
        <div className="pg">
          <button data-pg="-1" disabled={view.page === 0} onClick={() => setQuery({ ...query, page: view.page - 1 })}>
            ‹
          </button>
          <span className="pgl">{`${view.page + 1} / ${view.pages}`}</span>
          <button data-pg="1" disabled={view.page >= view.pages - 1} onClick={() => setQuery({ ...query, page: view.page + 1 })}>
            ›
          </button>
        </div>
      </div>
    </>
  );
}
