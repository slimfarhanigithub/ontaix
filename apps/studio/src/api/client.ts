/**
 * Typed client of the Ontaix API. The base URL comes from `VITE_ONTAIX_API_URL`; without one
 * the Studio talks to `/api/v1`, which the in-browser mock answers in dev and test-hook builds.
 * Against a real API, `connectRealApi` (./real) adds the live events the responses carry.
 *
 * Drafts leave in the contract's shape (./drafts). A `503 busy` means nothing was written, so the
 * request is sent once more after its `Retry-After` (at most 3 s) before the error reaches the caller.
 *
 * The session is a cookie the browser keeps (./session holds its CSRF token). A `401` from any
 * call other than sign-in and the session read means the session ended, and a
 * `403 password_change_required` that the password must be changed first; both are raised as
 * auth signals for the shell before the error reaches the caller.
 */
import { contractDraft } from './drafts';
import { authSignals, currentCsrfToken, forgetSession, rememberSession } from './session';
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
  type Organization,
  type OrganizationCreate,
  type OrganizationUpdate,
  type OrganizationUser,
  type OrganizationUserCreate,
  type OrganizationUserUpdate,
  type PasswordChange,
  type PlatformAuditEntry,
  type Session,
  type SignInRequest,
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
  type ImportDetection,
  type ImportMediaType,
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
  type TeachStreamEvent,
  type TeachStreamListener,
  type ViewState,
} from './types';

export const API_BASE: string = (import.meta.env.VITE_ONTAIX_API_URL as string | undefined) || '/api/v1';

/**
 * Dev builds only: the user the API's dev environment resolves from `X-Ontaix-User`, sent only
 * when `?user=<email>` is in the URL or `VITE_ONTAIX_DEV_USER` is set. Without either, a dev
 * build sends no identity header and signs in like a production build, which compiles this away.
 */
const IDENTITY: Record<string, string> = import.meta.env.DEV ? devIdentity() : {};

function devIdentity(): Record<string, string> {
  const user = new URLSearchParams(location.search).get('user') || (import.meta.env.VITE_ONTAIX_DEV_USER as string | undefined) || '';
  return user ? { 'X-Ontaix-User': user } : {};
}

/** True while this build sends the development identity header. */
export function hasDevIdentity(): boolean {
  return 'X-Ontaix-User' in IDENTITY;
}

/** Sign-in and the session read answer `401` about the credentials, not about a session that ended. */
const SESSION_FREE_PATHS = new Set(['/auth/sign-in', '/auth/session']);

const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

const BUSY_RETRY_CAP_MS = 3000;
const BUSY_RETRY_DEFAULT_MS = 1000;

async function call<R>(method: string, path: string, body?: unknown): Promise<R> {
  const res = await answered(method, path, body);
  if (res.status === 204) return undefined as R;
  return (await res.json()) as R;
}

/** The successful response of a request; a refusal is thrown as an ApiError, after one resend for `busy`. */
async function answered(method: string, path: string, body?: unknown): Promise<Response> {
  let res = await send(method, path, body);
  let problem = res.ok ? null : await problemOf(res);
  if (problem?.code === 'busy') {
    await new Promise((resolve) => setTimeout(resolve, busyRetryDelayMs(res.headers.get('Retry-After'))));
    res = await send(method, path, body);
    problem = res.ok ? null : await problemOf(res);
  }
  if (problem) {
    if (!SESSION_FREE_PATHS.has(path)) {
      if (res.status === 401) authSignals.emit('ended');
      else if (res.status === 403 && problem.code === 'password_change_required') authSignals.emit('passwordChangeRequired');
    }
    throw new ApiError(res.status, problem, retryAfterSeconds(res.headers.get('Retry-After')));
  }
  return res;
}

/** A stream that ends without its result line: nothing was lost on the server, so the sentence is taught again. */
const UNFINISHED: Problem = {
  title: 'Unavailable',
  status: 503,
  code: 'unavailable',
  detail: 'The sentence could not be read to the end; teach it again.',
};

/**
 * `POST /teach/parse/stream`: hands each draft and retract line to `listen` as it arrives and
 * resolves with the result line, the body `POST /teach/parse` answers. An error line is thrown as
 * an ApiError, like a refusal. A listener that fails never stops the parse.
 */
async function teachParseStream(body: TeachRequest, listen: TeachStreamListener): Promise<TeachResult> {
  const res = await answered('POST', '/teach/parse/stream', body);
  let result: TeachResult | null = null;
  const take = (line: string): void => {
    if (!line.trim()) return;
    const event = JSON.parse(line) as TeachStreamEvent;
    if (event.type === 'result') result = event.result;
    else if (event.type === 'error') throw new ApiError(event.problem.status, event.problem);
    else
      try {
        listen(event);
      } catch (err) {
        console.error('a streamed draft could not be shown', err);
      }
  };
  const reader = res.body?.getReader();
  if (!reader) {
    for (const line of (await res.text()).split('\n')) take(line);
  } else {
    const decoder = new TextDecoder();
    let rest = '';
    for (;;) {
      const { done, value } = await reader.read();
      rest += done ? decoder.decode() : decoder.decode(value, { stream: true });
      const lines = rest.split('\n');
      rest = lines.pop() ?? '';
      for (const line of lines) take(line);
      if (done) break;
    }
    take(rest);
  }
  if (!result) throw new ApiError(UNFINISHED.status, UNFINISHED);
  return result;
}

/**
 * A form body goes as multipart with the boundary the browser picks; anything else as JSON. The
 * session cookie travels with every call, and every unsafe method carries the session's CSRF token.
 */
function send(method: string, path: string, body: unknown): Promise<Response> {
  const headers: Record<string, string> = { ...IDENTITY };
  const csrf = currentCsrfToken();
  if (csrf && UNSAFE_METHODS.has(method)) headers['X-CSRF-Token'] = csrf;
  if (body instanceof FormData) return fetch(API_BASE + path, { method, headers, body, credentials: 'same-origin' });
  if (body !== undefined) headers['content-type'] = 'application/json';
  return fetch(API_BASE + path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: 'same-origin',
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
  /** Parses one sentence. With `listen`, the model's answer is streamed (`POST /teach/parse/stream`) and
   * `listen` receives each draft as soon as it is known; the result is the same either way. */
  teachParse: (body: TeachRequest, listen?: TeachStreamListener) =>
    listen ? teachParseStream(body, listen) : call<TeachResult>('POST', '/teach/parse', body),
  speechToken: (companyId: string) => call<SpeechToken>('POST', '/speech/token', { companyId }),
  importSentences: (file: File, mediaType?: ImportMediaType) => {
    const form = new FormData();
    form.append('file', file, file.name);
    if (mediaType) form.append('mediaType', mediaType);
    return call<ImportResult>('POST', '/import/sentences', form);
  },
  detectImport: (file: File) => {
    const form = new FormData();
    form.append('file', file, file.name);
    return call<ImportDetection>('POST', '/import/detect', form);
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

  signIn: (body: SignInRequest) => call<Session>('POST', '/auth/sign-in', body).then(rememberSession),
  signOut: () => call<void>('POST', '/auth/sign-out').finally(forgetSession),
  getSession: () => call<Session>('GET', '/auth/session').then(rememberSession),
  changePassword: (body: PasswordChange) => call<Session>('PUT', '/auth/password', body).then(rememberSession),

  listOrganizations: (p?: ListParams) => call<Paged<Organization>>('GET', `/admin/organizations${listQuery(p)}`),
  createOrganization: (body: OrganizationCreate) => call<Organization>('POST', '/admin/organizations', body),
  getOrganization: (id: string) => call<Organization>('GET', `/admin/organizations/${id}`),
  updateOrganization: (id: string, patch: OrganizationUpdate) => call<Organization>('PATCH', `/admin/organizations/${id}`, patch),
  disableOrganization: (id: string) => call<Organization>('POST', `/admin/organizations/${id}/disable`),
  enableOrganization: (id: string) => call<Organization>('POST', `/admin/organizations/${id}/enable`),
  listOrganizationGroups: (id: string) => call<Group[]>('GET', `/admin/organizations/${id}/groups`),
  listOrganizationUsers: (id: string, p?: ListParams) =>
    call<Paged<OrganizationUser>>('GET', `/admin/organizations/${id}/users${listQuery(p)}`),
  createOrganizationUser: (id: string, body: OrganizationUserCreate) =>
    call<OrganizationUser>('POST', `/admin/organizations/${id}/users`, body),
  getOrganizationUser: (id: string, userId: string) => call<OrganizationUser>('GET', `/admin/organizations/${id}/users/${userId}`),
  updateOrganizationUser: (id: string, userId: string, patch: OrganizationUserUpdate) =>
    call<OrganizationUser>('PATCH', `/admin/organizations/${id}/users/${userId}`, patch),
  disableOrganizationUser: (id: string, userId: string) =>
    call<OrganizationUser>('POST', `/admin/organizations/${id}/users/${userId}/disable`),
  enableOrganizationUser: (id: string, userId: string) =>
    call<OrganizationUser>('POST', `/admin/organizations/${id}/users/${userId}/enable`),
  resetOrganizationUserPassword: (id: string, userId: string, newPassword: string) =>
    call<void>('PUT', `/admin/organizations/${id}/users/${userId}/password`, { newPassword }),
  startSupportSession: (id: string, reason: string) =>
    call<Session>('POST', `/admin/organizations/${id}/support-session`, { reason }).then(rememberSession),
  endSupportSession: () => call<Session>('DELETE', '/admin/support-session').then(rememberSession),
  listPlatformAudit: (p?: ListParams) => call<Paged<PlatformAuditEntry>>('GET', `/admin/audit${listQuery(p)}`),
};

export type Api = typeof api;
