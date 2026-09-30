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
  type Agent,
  type AuditEntry,
  type ConnectorType,
  type CostSummary,
  type CrossCompanyDisabled,
  type Discovery,
  type DiscoveryRequest,
  type Group,
  type GroupInput,
  type RefreshAllResult,
  type RoleAssignment,
  type RoleGroup,
  type RoleInfo,
  type RoleName,
  type Scope,
  type Source,
  type SourceUpdate,
  type User,
  type BulkResult,
  type BranchResult,
  type DocumentExtraction,
  type DocumentExtractionResult,
  type ExpansionRequest,
  type ExpansionResult,
  type CompanyCreate,
  type CompanyCreated,
  type DecisionResult,
  type DomainProduct,
  type ImportResult,
  type OntologyImportRequest,
  type OntologyImportResult,
  type Page,
  type Problem,
  type Proposal,
  type ProposalDraft,
  type Scene,
  type Settings,
  type SettingsPatch,
  type SpeechToken,
  type TeachRequest,
  type TeachResult,
  type ViewState,
} from './types';

export const API_BASE: string = (import.meta.env.VITE_ONTAIX_API_URL as string | undefined) || '/api/v1';

/**
 * Dev builds only: the user the API's dev environment resolves from `X-Ontaix-User`. `?user=<email>`
 * overrides `VITE_ONTAIX_DEV_USER`, whose default is the seed's full-access demo user. A
 * production build compiles this away and sends no identity header.
 */
const IDENTITY: Record<string, string> = import.meta.env.DEV ? devIdentity() : {};

function devIdentity(): Record<string, string> {
  const user =
    new URLSearchParams(location.search).get('user') ||
    (import.meta.env.VITE_ONTAIX_DEV_USER as string | undefined) ||
    'demo@northwind.com';
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
  if (problem) throw new ApiError(res.status, problem, retryAfterSeconds(res.headers.get('Retry-After')));
  if (res.status === 204) return undefined as R;
  return (await res.json()) as R;
}

/** A form body goes as multipart with the boundary the browser picks; anything else as JSON. */
function send(method: string, path: string, body: unknown): Promise<Response> {
  if (body instanceof FormData) return fetch(API_BASE + path, { method, headers: { ...IDENTITY }, body });
  return fetch(API_BASE + path, {
    method,
    headers: body === undefined ? { ...IDENTITY } : { ...IDENTITY, 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

async function problemOf(res: Response): Promise<Problem> {
  return res.json().catch(() => ({ title: res.statusText, status: res.status, code: 'unknown' }));
}

function retryAfterSeconds(value: string | null): number | null {
  const seconds = Number(value);
  return value && Number.isFinite(seconds) && seconds >= 0 ? seconds : null;
}

/** `Retry-After` in seconds as a delay, capped at 3 s; a missing or unreadable value waits 1 s. */
export function busyRetryDelayMs(retryAfter: string | null): number {
  const seconds = Number(retryAfter);
  if (!retryAfter || !Number.isFinite(seconds) || seconds < 0) return BUSY_RETRY_DEFAULT_MS;
  return Math.min(seconds * 1000, BUSY_RETRY_CAP_MS);
}

/** Query parameters of a list operation: paging, search, `filter[field]`, sort and order. */
export interface ListParams {
  page?: number;
  pageSize?: number;
  q?: string;
  filter?: Record<string, string>;
  sort?: string;
  order?: 'asc' | 'desc';
}

export function listQuery(p: ListParams = {}): string {
  const parts: string[] = [];
  const add = (k: string, v: string | number) => parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  if (p.page !== undefined) add('page', p.page);
  if (p.pageSize !== undefined) add('pageSize', p.pageSize);
  if (p.q) add('q', p.q);
  for (const [k, v] of Object.entries(p.filter || {})) add(`filter[${k}]`, v);
  if (p.sort) add('sort', p.sort);
  if (p.order) add('order', p.order);
  return parts.length ? `?${parts.join('&')}` : '';
}

type Paged<T> = Page & { items: T[] };

export const api = {
  getScene: () => call<Scene>('GET', '/scene'),
  listProposals: () => call<Page & { items: Proposal[] }>('GET', '/proposals'),
  createProposal: (draft: ProposalDraft) => call<Proposal>('POST', '/proposals', contractDraft(draft)),
  createProposalBatch: (drafts: ProposalDraft[], parseId?: string | null) =>
    call<Proposal[]>('POST', '/proposals/batch', {
      drafts: drafts.map(contractDraft),
      ...(parseId ? { parseId } : {}),
    }),
  approve: (id: string) => call<DecisionResult>('POST', `/proposals/${id}/approve`),
  secondApprove: (id: string) => call<DecisionResult>('POST', `/proposals/${id}/second-approve`),
  reject: (id: string, reason?: string) =>
    call<DecisionResult>('POST', `/proposals/${id}/reject`, reason ? { reason } : undefined),
  approveAll: () => call<BulkResult>('POST', '/proposals/approve-all'),
  rejectAll: () => call<BulkResult>('POST', '/proposals/reject-all'),
  approveBranch: (id: string) => call<BranchResult>('POST', `/proposals/${id}/approve-branch`),
  expandConcept: (conceptId: string, body: ExpansionRequest) =>
    call<ExpansionResult>('POST', `/concepts/${conceptId}/expand`, body),
  proposeExpansion: (expansionId: string, indexes: number[]) =>
    call<Proposal[]>('POST', `/expansions/${expansionId}/proposals`, { indexes }),
  startDocumentExtraction: (importId: string, companyId: string) =>
    call<DocumentExtraction>('POST', `/import/${importId}/extraction`, { companyId }),
  getDocumentExtraction: (id: string) => call<DocumentExtraction>('GET', `/extractions/${id}`),
  cancelDocumentExtraction: (id: string) => call<DocumentExtraction>('DELETE', `/extractions/${id}`),
  getDocumentExtractionResult: (id: string) => call<DocumentExtractionResult>('GET', `/extractions/${id}/result`),
  proposeDocumentExtraction: (id: string, indexes: number[]) =>
    call<Proposal[]>('POST', `/extractions/${id}/proposals`, { indexes }),
  createCompany: (body: CompanyCreate) => call<CompanyCreated>('POST', '/companies', body),
  updateDomainProduct: (id: string, patch: { hidden?: boolean }) =>
    call<DomainProduct>('PATCH', `/domain-products/${id}`, patch),
  patchSettings: (patch: SettingsPatch) => call<Settings>('PATCH', '/settings', patch),
  patchAppearance: (patch: AppearancePatch) => call<Appearance>('PATCH', '/appearance', patch),
  putViewState: (state: Partial<ViewState>) => call<ViewState>('PUT', '/view-state', state),
  teachParse: (body: TeachRequest) => call<TeachResult>('POST', '/teach/parse', body),
  speechToken: (companyId: string) => call<SpeechToken>('POST', '/speech/token', { companyId }),
  importSentences: (file: File) => {
    const form = new FormData();
    form.append('file', file, file.name);
    return call<ImportResult>('POST', '/import/sentences', form);
  },
  importOntology: (file: File, body: OntologyImportRequest) => {
    const form = new FormData();
    form.append('file', file, file.name);
    for (const [key, value] of Object.entries(body)) if (value !== undefined) form.append(key, value);
    return call<OntologyImportResult>('POST', '/ontology-imports', form);
  },
  getOntologyImport: (id: string) => call<OntologyImportResult>('GET', `/ontology-imports/${id}`),
  proposeOntologyImport: (id: string, indexes: number[]) =>
    call<Proposal[]>('POST', `/ontology-imports/${id}/proposals`, { indexes }),

  listConnectors: () => call<ConnectorType[]>('GET', '/connectors'),
  discover: (code: string, body: DiscoveryRequest) =>
    call<Discovery>('POST', `/connectors/${encodeURIComponent(code)}/discover`, body),
  getSource: (id: string) => call<Source>('GET', `/sources/${id}`),
  updateSource: (id: string, patch: SourceUpdate) => call<Source>('PATCH', `/sources/${id}`, patch),
  enableSource: (id: string) => call<Source>('POST', `/sources/${id}/enable`),
  disableSource: (id: string) => call<Source>('POST', `/sources/${id}/disable`),
  refreshAllSources: () => call<RefreshAllResult>('POST', '/sources/refresh-all'),
  proposeRemoveSource: (id: string) => call<Proposal>('DELETE', `/sources/${id}`),
  proposeUnbind: (bindingId: string) => call<Proposal>('DELETE', `/bindings/${bindingId}`),
  proposeRemoveCompany: (id: string) => call<Proposal>('DELETE', `/companies/${id}`),
  listUsers: (p?: ListParams) => call<Paged<User>>('GET', `/users${listQuery(p)}`),
  listGroups: (p?: ListParams) => call<Paged<Group>>('GET', `/groups${listQuery(p)}`),
  getGroup: (id: string) => call<Group>('GET', `/groups/${id}`),
  createGroup: (body: GroupInput) => call<Group>('POST', '/groups', body),
  updateGroup: (id: string, body: GroupInput) => call<Group>('PATCH', `/groups/${id}`, body),
  deleteGroup: (id: string) => call<void>('DELETE', `/groups/${id}`),
  addGroupMember: (groupId: string, userId: string) => call<void>('PUT', `/groups/${groupId}/members/${userId}`),
  removeGroupMember: (groupId: string, userId: string) => call<void>('DELETE', `/groups/${groupId}/members/${userId}`),
  addGroupRole: (groupId: string, body: { role: RoleName; scope: Scope }) =>
    call<RoleAssignment>('POST', `/groups/${groupId}/roles`, body),
  removeGroupRole: (groupId: string, assignmentId: string) => call<void>('DELETE', `/groups/${groupId}/roles/${assignmentId}`),
  listRoles: () => call<RoleInfo[]>('GET', '/roles'),
  listRoleGroups: (role: RoleName) => call<RoleGroup[]>('GET', `/roles/${role}/groups`),
  listScopes: () => call<Scope[]>('GET', '/scopes'),
  listAgents: (p?: ListParams) => call<Paged<Agent>>('GET', `/agents${listQuery(p)}`),
  updateAgent: (id: string, access: boolean) => call<Agent>('PATCH', `/agents/${id}`, { access }),
  getCost: () => call<CostSummary>('GET', '/cost'),
  disableCrossCompany: (confirmation: string) =>
    call<CrossCompanyDisabled>('POST', '/settings/cross-company/disable', { confirmation }),
  resetAppearance: () => call<Appearance>('POST', '/appearance/reset'),
  listAudit: (p?: ListParams) => call<Paged<AuditEntry>>('GET', `/audit${listQuery(p)}`),
};

export type Api = typeof api;
