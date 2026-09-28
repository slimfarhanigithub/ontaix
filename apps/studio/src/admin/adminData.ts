/**
 * Directory data the admin portal reads through the API: groups, users and the audit log, which
 * the navigation counts and several pages share. Loaded when the portal renders from scratch.
 * A refused or unavailable call leaves the list empty and shows a toast; nothing throws.
 */
import { api, type ListParams } from '../api/client';
import { ApiError, type AuditEntry, type Group, type Page, type User } from '../api/types';
import { store } from '../store/store';

/** The audit page shows the newest 120 entries. */
export const AUDIT_SHOWN = 120;

export interface DirectoryState {
  groups: Group[];
  users: User[];
  audit: AuditEntry[];
  auditTotal: number;
  /** Portal render the lists were loaded for; -1 before the first load. */
  rev: number;
}

export const directory: DirectoryState = { groups: [], users: [], audit: [], auditTotal: 0, rev: -1 };

let loadedRev = -1;

/** Every row of a paged list, 200 at a time. */
export async function fetchAll<T>(get: (p: ListParams) => Promise<Page & { items: T[] }>): Promise<T[]> {
  const out: T[] = [];
  for (let page = 1; page < 1000; page++) {
    const r = await get({ page, pageSize: 200 });
    out.push(...r.items);
    if (!r.items.length || out.length >= r.total) break;
  }
  return out;
}

/** A failed call as the reference's toast; anything that is not an API refusal is logged. */
export function failed(err: unknown, lead = 'Refused'): void {
  if (err instanceof ApiError) store.toast2(lead, err.problem.detail || err.problem.title);
  else console.error('admin call failed', err);
}

/** Runs an API call; a refusal becomes a toast and the result is null. */
export async function attempt<T>(call: () => Promise<T>): Promise<T | null> {
  try {
    return await call();
  } catch (err) {
    failed(err);
    return null;
  }
}

/** Loads groups, users and the audit log once per portal render. */
export async function loadDirectory(rev: number): Promise<void> {
  if (rev === loadedRev) return;
  loadedRev = rev;
  let refusal: unknown = null;
  const soft = <T>(p: Promise<T>): Promise<T | null> =>
    p.catch((err: unknown) => {
      refusal = refusal || err;
      return null;
    });
  const [groups, users, audit] = await Promise.all([
    soft(fetchAll((p) => api.listGroups(p))),
    soft(fetchAll((p) => api.listUsers(p))),
    soft(api.listAudit({ page: 1, pageSize: AUDIT_SHOWN })),
  ]);
  if (refusal) failed(refusal, 'Unavailable');
  directory.groups = groups || [];
  directory.users = users || [];
  directory.audit = audit ? audit.items : [];
  directory.auditTotal = audit ? audit.total : 0;
  directory.rev = rev;
  store.bump();
}

/** Forces the next portal render to reload the directory. */
export function invalidateDirectory(): void {
  loadedRev = -1;
}
