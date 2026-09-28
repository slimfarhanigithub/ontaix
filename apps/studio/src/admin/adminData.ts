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
  /** True once a load has answered, refused or not. */
  loaded: boolean;
}

export const directory: DirectoryState = { groups: [], users: [], audit: [], auditTotal: 0, loaded: false };

let stale = true;
let loadSeq = 0;

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

/**
 * Loads groups, users and the audit log when they are stale: when the portal opens and after
 * an action changed them. Moving between pages reuses what is loaded. Only the latest load
 * lands, so an older answer never overwrites a newer one.
 */
export async function loadDirectory(): Promise<void> {
  if (!stale) return;
  stale = false;
  const seq = ++loadSeq;
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
  if (seq !== loadSeq) return;
  if (refusal) failed(refusal, 'Unavailable');
  directory.groups = groups || [];
  directory.users = users || [];
  directory.audit = audit ? audit.items : [];
  directory.auditTotal = audit ? audit.total : 0;
  directory.loaded = true;
  store.bump();
}

/** Marks the directory stale; the next portal render reloads it. */
export function invalidateDirectory(): void {
  stale = true;
}
