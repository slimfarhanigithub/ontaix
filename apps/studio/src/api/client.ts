/**
 * Typed client of the Ontaix API. The base URL comes from `VITE_ONTAIX_API_URL`; without one
 * the Studio talks to `/api/v1`, which the in-browser mock answers.
 */
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
  type Proposal,
  type ProposalDraft,
  type Scene,
  type Settings,
  type SettingsPatch,
  type TeachResult,
  type ViewState,
} from './types';

export const API_BASE: string = (import.meta.env.VITE_ONTAIX_API_URL as string | undefined) || '/api/v1';

async function call<R>(method: string, path: string, body?: unknown): Promise<R> {
  const res = await fetch(API_BASE + path, {
    method,
    headers: body === undefined ? undefined : { 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const problem = await res.json().catch(() => ({ title: res.statusText, status: res.status, code: 'unknown' }));
    throw new ApiError(res.status, problem);
  }
  return (await res.json()) as R;
}

export const api = {
  getScene: () => call<Scene>('GET', '/scene'),
  listProposals: () => call<Page & { items: Proposal[] }>('GET', '/proposals'),
  createProposal: (draft: ProposalDraft) => call<Proposal>('POST', '/proposals', draft),
  createProposalBatch: (drafts: ProposalDraft[]) => call<Proposal[]>('POST', '/proposals/batch', { drafts }),
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
