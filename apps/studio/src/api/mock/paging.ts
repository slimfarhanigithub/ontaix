/**
 * The contract's list query for the mock's paged lists: `page`, `pageSize`, `q`, `filter[field]`,
 * `sort` and `order`, and one page of rows after search, filters and sort.
 */

export class PagingRefusal extends Error {
  constructor(
    public status: number,
    public code: string,
    public detail: string,
  ) {
    super(detail);
  }
}

export interface ListArgs {
  page: number;
  pageSize: number;
  q: string;
  filter: Record<string, string>;
  sort: string | null;
  order: 'asc' | 'desc';
}

/** Parses the contract's list query (`page`, `pageSize`, `q`, `filter[field]`, `sort`, `order`). */
export function parseListArgs(search: string): ListArgs {
  const p = new URLSearchParams(search);
  const filter: Record<string, string> = {};
  for (const [k, v] of p.entries()) {
    const m = /^filter\[(.+)\]$/.exec(k);
    if (m) filter[m[1]] = v;
  }
  const size = Math.min(200, Math.max(1, Number(p.get('pageSize')) || 40));
  return {
    page: Math.max(1, Number(p.get('page')) || 1),
    pageSize: size,
    q: (p.get('q') || '').toLowerCase(),
    filter,
    sort: p.get('sort'),
    order: p.get('order') === 'desc' ? 'desc' : 'asc',
  };
}

/** One page of rows after search, filters and sort; rows keep their natural order unless sorted. */
export function pageOf<R>(
  rows: R[],
  args: ListArgs,
  fields: { search: (r: R) => string[]; filters: Record<string, (r: R) => string>; sorts: Record<string, (r: R) => string | number> },
): { items: R[]; page: number; pageSize: number; total: number } {
  for (const k of Object.keys(args.filter))
    if (!fields.filters[k]) throw new PagingRefusal(400, 'unknown_filter', `${k} is not a filter of this list`);
  if (args.sort && !fields.sorts[args.sort]) throw new PagingRefusal(400, 'unknown_sort', `${args.sort} is not a sort field of this list`);
  let list = rows.filter(
    (r) =>
      Object.entries(args.filter).every(([k, v]) => v.split(',').includes(fields.filters[k](r))) &&
      (!args.q || fields.search(r).some((s) => s.toLowerCase().includes(args.q))),
  );
  if (args.sort) {
    const key = fields.sorts[args.sort],
      dir = args.order === 'desc' ? -1 : 1;
    list = list.slice().sort((a, b) => {
      const x = key(a),
        y = key(b);
      return (x > y ? 1 : x < y ? -1 : 0) * dir;
    });
  }
  const start = (args.page - 1) * args.pageSize;
  return { items: list.slice(start, start + args.pageSize), page: args.page, pageSize: args.pageSize, total: list.length };
}
