/**
 * Typed client of the Ontaix API. The base URL comes from `VITE_ONTAIX_API_URL`; without one
 * the Studio talks to `/api/v1`, which the in-browser mock answers in dev and test-hook builds.
 * Against a real API, `connectRealApi` (./real) adds the live events the responses carry.
 *
 * Drafts leave in the contract's shape (./drafts). A `503 busy` means nothing was written, so the
 * request is sent once more after its `Retry-After` (at most 3 s) before the error reaches the caller.
 */
import { contractDraft } from './drafts';
import {
  ApiError,
  type AppearancePatch,
  type Appearance,
  type BulkResult,
  type CompanyCreate,
  type CompanyCreated,
  type DecisionResult,
  type DemoNext,
  type DemoScenes,
  type DomainProduct,
  type FinaliseResult,
  type Page,
  type Problem,
  type Proposal,
  type ProposalDraft,
  type Scene,
  type Settings,
  type SettingsPatch,
  type TeachResult,
  type ViewState,
} from './types';

export const API_BASE: string = (import.meta.env.VITE_ONTAIX_API_URL as string | undefined) || '/api/v1';

/**
 * Dev builds only: the user the API's dev environment resolves from `X-Ontaix-User`. `?user=<email>`
 * overrides `VITE_ONTAIX_DEV_USER`, whose default is the seed's Builder. A production build
 * compiles this away and sends no identity header.
 */
const IDENTITY: Record<string, string> = import.meta.env.DEV ? devIdentity() : {};

function devIdentity(): Record<string, string> {
  const user =
    new URLSearchParams(location.search).get('user') ||
    (import.meta.env.VITE_ONTAIX_DEV_USER as string | undefined) ||
    'sam.okafor@northwind.com';
  return { 'X-Ontaix-User': user };
}

const BUSY_RETRY_CAP_MS = 3000;
const BUSY_RETRY_DEFAULT_MS = 1000;

async function call<R>(method: string, path: string, body?: unknown): Promise<R> {
  let res = await send(method, path, body);
  let problem = res.ok ? null : await problemOf(res);
  if (problem?.code === 'busy') {
    await new Promise((resolve) => setTimeout(resolve, busyRetryDelayMs(res.headers.get('Retry-After'))));
    res = await send(method, path, body);
    problem = res.ok ? null : await problemOf(res);
  }
  if (problem) throw new ApiError(res.status, problem);
  return (await res.json()) as R;
}

function send(method: string, path: string, body: unknown): Promise<Response> {
  return fetch(API_BASE + path, {
    method,
    headers: body === undefined ? { ...IDENTITY } : { ...IDENTITY, 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

async function problemOf(res: Response): Promise<Problem> {
  return res.json().catch(() => ({ title: res.statusText, status: res.status, code: 'unknown' }));
}

/** `Retry-After` in seconds as a delay, capped at 3 s; a missing or unreadable value waits 1 s. */
export function busyRetryDelayMs(retryAfter: string | null): number {
  const seconds = Number(retryAfter);
  if (!retryAfter || !Number.isFinite(seconds) || seconds < 0) return BUSY_RETRY_DEFAULT_MS;
  return Math.min(seconds * 1000, BUSY_RETRY_CAP_MS);
}

export const api = {
  getScene: () => call<Scene>('GET', '/scene'),
  listProposals: () => call<Page & { items: Proposal[] }>('GET', '/proposals'),
  createProposal: (draft: ProposalDraft) => call<Proposal>('POST', '/proposals', contractDraft(draft)),
  createProposalBatch: (drafts: ProposalDraft[]) =>
    call<Proposal[]>('POST', '/proposals/batch', { drafts: drafts.map(contractDraft) }),
  approve: (id: string) => call<DecisionResult>('POST', `/proposals/${id}/approve`),
  secondApprove: (id: string) => call<DecisionResult>('POST', `/proposals/${id}/second-approve`),
  reject: (id: string, reason?: string) =>
    call<DecisionResult>('POST', `/proposals/${id}/reject`, reason ? { reason } : undefined),
  approveAll: () => call<BulkResult>('POST', '/proposals/approve-all'),
  rejectAll: () => call<BulkResult>('POST', '/proposals/reject-all'),
  finaliseAll: () => call<FinaliseResult>('POST', '/proposals/finalise-all'),
  createCompany: (body: CompanyCreate) => call<CompanyCreated>('POST', '/companies', body),
  updateDomainProduct: (id: string, patch: { hidden?: boolean }) =>
    call<DomainProduct>('PATCH', `/domain-products/${id}`, patch),
  patchSettings: (patch: SettingsPatch) => call<Settings>('PATCH', '/settings', patch),
  patchAppearance: (patch: AppearancePatch) => call<Appearance>('PATCH', '/appearance', patch),
  putViewState: (state: Partial<ViewState>) => call<ViewState>('PUT', '/view-state', state),
  teachParse: (body: { companyId: string; text: string; fromImport?: boolean }) =>
    call<TeachResult>('POST', '/teach/parse', body),
  demoScenes: () => call<DemoScenes>('GET', '/demo/scenes'),
  demoNext: () => call<DemoNext>('POST', '/demo/next'),
  demoReset: () => call<Scene>('POST', '/demo/reset'),
};

export type Api = typeof api;
