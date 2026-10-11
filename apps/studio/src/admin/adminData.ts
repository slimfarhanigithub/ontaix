/**
 * Data the admin portal reads through the API and several pages share: the audit log, which the
 * navigation counts. Loaded when the portal renders from scratch. A refused or unavailable call
 * leaves the list empty and shows a toast; nothing throws.
 */
import { api, type ListParams } from '../api/client';
import { ApiError, type AuditEntry, type Page } from '../api/types';
import { store } from '../store/store';

/** The audit page shows the newest 120 entries. */
export const AUDIT_SHOWN = 120;

export interface DirectoryState {
  audit: AuditEntry[];
  auditTotal: number;
  /** True once a load has answered, refused or not. */
  loaded: boolean;
}

export const directory: DirectoryState = { audit: [], auditTotal: 0, loaded: false };

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
 * Loads the audit log when it is stale: when the portal opens and after an action changed it.
 * Moving between pages reuses what is loaded. Only the latest load lands, so an older answer
 * never overwrites a newer one.
 */
export async function loadDirectory(): Promise<void> {
  if (!stale) return;
  stale = false;
  const seq = ++loadSeq;
  let audit: (Page & { items: AuditEntry[] }) | null = null;
  try {
    audit = await api.listAudit({ page: 1, pageSize: AUDIT_SHOWN });
  } catch (err) {
    if (seq !== loadSeq) return;
    failed(err, 'Unavailable');
  }
  if (seq !== loadSeq) return;
  directory.audit = audit ? audit.items : [];
  directory.auditTotal = audit ? audit.total : 0;
  directory.loaded = true;
  store.bump();
}

/** A new session or organization: the audit log is forgotten, and a load still in flight for the previous one lands nowhere. */
export function resetDirectory(): void {
  loadSeq++;
  stale = true;
  directory.audit = [];
  directory.auditTotal = 0;
  directory.loaded = false;
}

/** Marks the audit log stale; the next portal render reloads it. */
export function invalidateDirectory(): void {
  stale = true;
}
