/**
 * Shapes of the Ontaix API as contracts/openapi.yaml defines them, limited to what the Studio
 * canvas and the proposal flow read and write.
 */
import type { DomainKey } from '../canvas/types';

export type { DomainKey };

export type ActorKind = 'user' | 'agent' | 'system';

export interface Actor {
  kind: ActorKind;
  id?: string;
  name?: string;
}

export interface Company {
  id: string;
  key: string;
  name: string;
  sub: string;
  position: number;
  isHome: boolean;
  rootId: string;
  domainProducts: DomainProduct[];
  counts: {
    concepts: number;
    sources: number;
    equivalences: number;
    bound: number;
    percentBound: number;
    domainsWithCells: number;
  };
  dyingAt?: string | null;
}

export interface CompanyCreate {
  name: string;
  sub?: string;
  start: 'starter_vocabulary' | 'one_cell';
}

export interface CompanyCreated {
  company: Company;
  root: Concept;
  proposals: Proposal[];
}

export interface DomainProduct {
  id: string;
  companyId: string;
  key: DomainKey;
  name: string;
  owner: string;
  color: string;
  revision: number;
  version: string;
  hidden: boolean;
  counts: { members: number; pending: number; bound: number };
}

export type AttributeType = 'id' | 'text' | 'number' | 'ref' | 'date';

export interface Attribute {
  id: string;
  conceptId: string;
  sourceId?: string | null;
  name: string;
  type: AttributeType;
  col: string;
  fill: number;
  state: 'proposed' | 'approved';
}

export interface Binding {
  id: string;
  sourceId: string;
  sourceLabel: string;
  conceptId: string;
  records: number;
  fresh: string;
  pending: boolean;
}

export interface Concept {
  id: string;
  companyId: string;
  kind: 'root' | 'concept';
  label: string;
  sub: string;
  domainProductId?: string | null;
  domainKey?: DomainKey | null;
  color?: string;
  rule?: string | null;
  pending: boolean;
  conflict: boolean;
  parentId?: string | null;
  birthRelationId?: string | null;
  bornAt: string;
  x: number;
  y: number;
  pinned: boolean;
  dyingAt?: string | null;
  bound?: Binding | null;
  attributes: Attribute[];
  relationCount: number;
  state: 'awaiting approval' | 'approved' | 'certified';
  isSpecialisation?: boolean;
}

export type SourceAuth = 'service_principal' | 'oauth2_client_credentials' | 'managed_identity' | 'key_vault_api_key';
export type RefreshInterval = '5 min' | '15 min' | '1 h' | 'daily';

export interface Source {
  id: string;
  companyId: string;
  label: string;
  kindText: string;
  connectorCode?: string | null;
  host?: string | null;
  scope?: string | null;
  auth?: SourceAuth | null;
  refresh: RefreshInterval;
  anchorIndex: number;
  disabled: boolean;
  pending: boolean;
  x: number;
  y: number;
  pinned: boolean;
  dyingAt?: string | null;
  feeds: number;
  records: number | null;
  state: 'awaiting approval' | 'disabled' | 'connected';
}

export type RelationKind = 'rel' | 'isa' | 'same' | 'clash';

export interface Relation {
  id: string;
  aId: string;
  bId: string;
  aLabel: string;
  bLabel: string;
  kind: RelationKind;
  label: string;
  rest: number;
  seed: number;
  pending: boolean;
  dyingAt?: string | null;
  companyIds: string[];
  scope: string;
  state?: 'awaiting approval' | 'approved';
}

/** A scene node is a concept or a source; a scene link is a relation or a binding. */
export type SceneNode = Concept | Source;
export type SceneLink = Relation | Binding;

export const isSource = (n: SceneNode): n is Source => 'kindText' in n;
export const isBinding = (l: SceneLink): l is Binding => 'conceptId' in l;

/**
 * Curve bend of the relation a draft creates, drawn by the client from its random stream in
 * the reference's draw order and stored by the server on the relation. Absent, the server
 * draws it.
 */
export interface DraftSeed {
  seed?: number;
}

/** How a proposal's content entered Ontaix; `document`, `suggestion` and `ontology_import` are set by the server only. */
export type Origin = 'text' | 'speech' | 'document' | 'suggestion' | 'ontology_import';
/** The origin a client declares on a draft or a teach parse. */
export type InputOrigin = 'text' | 'speech';

/** Cites one stored sentence of a document import. */
export interface ImportRef {
  importId: string;
  sentenceIndex: number;
}

export interface DocumentPosition {
  unit: 'page' | 'paragraph';
  index: number;
}

export type ImportMediaType =
  | 'text/plain'
  | 'text/markdown'
  | 'text/csv'
  | 'application/json'
  | 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
  | 'application/pdf';

/** Where a `document` proposal came from, copied by the server from the stored import. */
export interface OriginDetail {
  fileName: string;
  mediaType: ImportMediaType;
  sentenceIndex: number;
  position?: DocumentPosition;
}

/** Provenance fields every draft may carry. */
export interface DraftOrigin {
  origin?: InputOrigin;
  importRef?: ImportRef;
}

/** `POST /import/sentences`: the stored import and its sentences. */
export interface ImportResult {
  importId: string;
  expiresAt: string;
  fileName: string;
  origin: 'document';
  originDetail: { fileName: string; mediaType: ImportMediaType };
  sentences: string[];
  positions?: (DocumentPosition | null)[];
}

export interface ConceptDraft extends DraftSeed, DraftOrigin {
  type: 'concept';
  companyId: string;
  parentId: string;
  parentLabel?: string;
  label: string;
  domainKey: DomainKey;
  action: string;
  reverse?: boolean;
  caption?: string;
}

export interface SpecDraft extends DraftSeed, DraftOrigin {
  type: 'spec';
  companyId: string;
  parentId: string;
  parentLabel?: string;
  label: string;
  rule?: string;
  domainKey: DomainKey;
  caption?: string;
}

export interface RelationDraft extends DraftSeed, DraftOrigin {
  type: 'relation';
  aId: string;
  bId: string;
  aLabel?: string;
  bLabel?: string;
  action: string;
  caption?: string;
}

export interface SourceDraft extends DraftOrigin {
  type: 'source';
  companyId: string;
  label: string;
  kindText: string;
  connectorCode?: string;
  host?: string;
  scope?: string;
  auth?: SourceAuth;
  refresh?: RefreshInterval;
  caption?: string;
}

export interface BindingDraft extends DraftOrigin {
  type: 'bind';
  sourceId: string;
  conceptIds: string[];
  caption?: string;
}

export interface AttributeDraft extends DraftOrigin {
  type: 'attr';
  conceptId: string;
  sourceId?: string;
  name: string;
  attributeType: AttributeType;
  col: string;
  fill: number;
}

export type ChangeKind =
  | 'rename'
  | 'delete_concept'
  | 'edit_relation'
  | 'remove_relation'
  | 'unbind'
  | 'remove_source'
  | 'remove_company'
  | 'rename_source'
  | 'resolve_conflict';

export interface ChangeDraft extends DraftOrigin {
  type: 'change';
  changeKind: ChangeKind;
  payload: {
    conceptId?: string;
    newLabel?: string;
    relationId?: string;
    action?: string;
    reverse?: boolean;
    bindingId?: string;
    sourceId?: string;
    companyId?: string;
    conflictConceptIds?: [string, string];
  };
  caption?: string;
}

export type ProposalDraft =
  | ConceptDraft
  | SpecDraft
  | RelationDraft
  | SourceDraft
  | BindingDraft
  | AttributeDraft
  | ChangeDraft;

export type ProposalType = ProposalDraft['type'];
export type ProposalState = 'pending' | 'half_approved' | 'approved' | 'rejected';

export interface Artefacts {
  concepts?: Concept[];
  relations?: Relation[];
  sources?: Source[];
  bindings?: Binding[];
  attributes?: Attribute[];
  domainProducts?: DomainProduct[];
  companies?: Company[];
}

export interface Proposal {
  id: string;
  type: ProposalType;
  changeKind?: ChangeKind | 'remove_cross_company_links' | null;
  state: ProposalState;
  title: string;
  heading?: string;
  color: string;
  companyId?: string | null;
  domainProductId?: string | null;
  parentLabel?: string | null;
  deps: string[];
  ready: boolean;
  waitFor?: string | null;
  html: string;
  why?: string | null;
  caption?: string | null;
  conceptId?: string | null;
  relationId?: string | null;
  relationIds: string[];
  sourceId?: string | null;
  bindingIds: string[];
  attributeId?: string | null;
  proposer: Actor;
  origin: Origin;
  originDetail: OriginDetail | null;
  approvals: { ordinal: 1 | 2; userId: string; userName?: string; approvedAt: string }[];
  bulk?: boolean;
  createdAt: string;
  decidedAt?: string | null;
  artefacts?: Artefacts;
  /** Open proposals in the branch of a `concept` or `spec` proposal other than itself; 0 or absent otherwise. */
  openBelow?: number;
}

export interface AuditEntry {
  id: number;
  at: string;
  actor: Actor;
  kind: string;
  what: string;
  ok: boolean;
  proposalId?: string | null;
  origin: Origin | null;
  companyIds: string[];
  domainKey?: DomainKey | null;
}

export interface DecisionResult {
  proposal: Proposal;
  artefacts: Artefacts;
  cascaded: Proposal[];
  audit: AuditEntry;
  caption?: string;
}

export interface BulkResult {
  approved: number;
  rejected: number;
  rounds: number;
  remaining: number;
  caption?: string;
}

export interface Settings {
  voice: boolean;
  importDocs: boolean;
  liveTeaching: boolean;
  everyoneTeaches: boolean;
  approvalRequired: true;
  twoApprovers: boolean;
  autoAttrs: boolean;
  notifyOwners: boolean;
  multiCompany: boolean;
  crossCompany: boolean;
  animations: boolean;
  coverageDefault: boolean;
  legend: boolean;
  readOnlyConnectors: true;
  refresh: RefreshInterval;
  agentAccess: boolean;
  costCap: boolean;
  /** Tokens Ontaix's own language model calls may use per UTC month; 0 turns the step off. */
  llmMonthlyTokenCap: number;
}

export type SettingsPatch = Partial<Omit<Settings, 'approvalRequired' | 'readOnlyConnectors'>>;

export interface Appearance {
  theme: 'dark' | 'light';
  colors: Record<string, string>;
  accent: string;
  source: string;
  defaults: { colors: Record<string, string>; accent: string; source: string };
}

export type AppearancePatch = Partial<Pick<Appearance, 'theme' | 'colors' | 'accent' | 'source'>>;

export interface ViewState {
  coverage: boolean;
}

export interface ConnectorType {
  code: string;
  name: string;
  category: string;
  scopeText: string;
}

export interface Scene {
  sequence: number;
  serverTime: string;
  companies: Company[];
  nodes: SceneNode[];
  links: SceneLink[];
  proposals: Proposal[];
  settings: Settings;
  appearance: Appearance;
  viewState: ViewState;
  connectors: ConnectorType[];
}

export interface Intent {
  kind: 'spec' | 'rel';
  subject: string;
  predicate?: string;
  object: string;
  rule?: string;
  subjectResolved: string | null;
  objectResolved: string | null;
}

/** A half-open range [start, end) of Unicode code points of the request's text. */
export interface SourceSpan {
  start: number;
  end: number;
}

export interface SourceSegment {
  index: number;
  span: SourceSpan;
}

/** Advisory notes on one draft for the reviewer; never submitted with the draft. */
export interface DraftNote {
  extractor: 'rules' | 'llm';
  confidence: number;
  explanation?: string;
  segment?: number;
  sourceSpan?: SourceSpan;
}

export interface UnresolvedPhrase {
  text: string;
  reason:
    | 'not_understood'
    | 'ambiguous_reference'
    | 'low_confidence'
    | 'model_unavailable'
    | 'model_invalid_output'
    | 'too_many_drafts'
    | 'not_a_statement'
    | 'ungrounded_label'
    | 'too_many_segments';
}

export type LlmOutcome =
  | 'not_triggered'
  | 'used'
  | 'not_configured'
  | 'rate_limited'
  | 'budget_exhausted'
  | 'timeout'
  | 'provider_error'
  | 'invalid_output';

export interface TeachResult {
  outcome: 'understood' | 'partly_understood' | 'not_understood';
  domainKey: DomainKey | null;
  intents: Intent[];
  drafts: ProposalDraft[];
  statements?: string[];
  caption: string;
  origin: Origin;
  originDetail: OriginDetail | null;
  extractor: 'rules' | 'llm' | 'rules+llm';
  degraded: boolean;
  llmOutcome: LlmOutcome;
  /** One per draft, same order. */
  draftNotes: DraftNote[];
  unresolved: UnresolvedPhrase[];
  /** The sentences the request was split into; one for typed text and documents. */
  segments: SourceSegment[];
}

/** `POST /teach/parse`: typed text or a speech transcript, or a cited import sentence. */
export interface TeachRequest {
  companyId: string;
  text?: string;
  origin?: InputOrigin;
  importRef?: ImportRef;
  /** One per teach bar session and company, so the model step can resolve back-references. */
  sessionId?: string;
}

// ------------------------------------------------------------ concept expansion

/** `POST /concepts/{conceptId}/expand`: optional steering from the caller. */
export interface ExpansionRequest {
  depth?: number;
  maxChildren?: number;
  focus?: string;
  sessionId?: string;
}

export type ExpansionOutcome =
  | 'used'
  | 'not_configured'
  | 'rate_limited'
  | 'budget_exhausted'
  | 'timeout'
  | 'provider_error'
  | 'refused'
  | 'invalid_output';

/** One note per expansion draft: confidence, rationale, depth (null for a relation) and the drafts it requires. */
export interface ExpansionNote {
  confidence: number;
  rationale: string;
  depth: number | null;
  requires: number[];
}

export interface ExpansionSkip {
  label: string;
  reason: 'existing_label' | 'duplicate_in_response' | 'low_confidence' | 'over_cap' | 'parent_skipped' | 'duplicate_relation';
}

/** Expansion drafts in the contract's shape: a concept by `parentId` or `parentLabel`, a relation by id or label ends. */
export type ExpansionDraft =
  | (Omit<ConceptDraft, 'parentId'> & { parentId?: string })
  | (Omit<RelationDraft, 'aId' | 'bId'> & { aId?: string; bId?: string; companyId?: string });

export interface ExpansionResult {
  expansionId: string | null;
  expiresAt: string | null;
  conceptId: string;
  llmOutcome: ExpansionOutcome;
  degraded: boolean;
  drafts: ExpansionDraft[];
  notes: ExpansionNote[];
  skipped: ExpansionSkip[];
}

// ------------------------------------------------------------ whole-document extraction

export type ExtractionState = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
export type ExtractionFailure =
  | 'not_configured'
  | 'budget_exhausted'
  | 'rate_limited'
  | 'job_timeout'
  | 'no_drafts'
  | 'import_expired'
  | 'too_many_attempts'
  | 'internal';

export interface DocumentExtraction {
  id: string;
  importId: string | null;
  companyId: string;
  state: ExtractionState;
  phase: 'outline' | 'sections' | 'mapping' | null;
  chunks: number;
  outlineChunksDone: number;
  sectionChunksDone: number;
  outlineNodes: number;
  tokensUsed: number;
  tokenCeiling: number;
  nodeCeiling: number;
  draftCount: number;
  degraded: boolean;
  failureReason: ExtractionFailure | null;
  cancelRequested: boolean;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  expiresAt: string | null;
  submittedAt: string | null;
}

export type OutlineRole = 'domain_area' | 'process' | 'subprocess' | 'step' | 'entity' | 'group';

export interface OutlineNode {
  index: number;
  parentIndex: number | null;
  parentConceptId?: string | null;
  conceptId: string | null;
  label: string;
  role: OutlineRole;
  depth: number;
  sentenceIndex: number;
}

export interface DocumentDraftNote {
  pass: 'outline' | 'section';
  confidence: number;
  explanation?: string;
  role?: OutlineRole;
  depth: number | null;
  requires: number[];
  sentenceIndex: number;
  sourceSpan?: { start: number; end: number };
}

export interface ExtractionUnresolved {
  chunk?: number;
  sentenceIndex?: number;
  label?: string;
  reason: string;
}

export interface DocumentExtractionResult {
  extractionId: string;
  outline: OutlineNode[];
  drafts: ProposalDraft[];
  notes: DocumentDraftNote[];
  unresolved: ExtractionUnresolved[];
}

/** `POST /proposals/{proposalId}/approve-branch`: what one call approved; `complete` false asks for another call. */
export interface BranchResult {
  rootId: string;
  approved: number;
  skipped: number;
  remaining: number;
  batches: number;
  complete: boolean;
}

export interface Page {
  page: number;
  pageSize: number;
  total: number;
}

export interface Problem {
  type?: string;
  title: string;
  status: number;
  detail?: string;
  code: string;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly problem: Problem,
    /** Seconds from the `Retry-After` header, when the API sent one. */
    public readonly retryAfter: number | null = null,
  ) {
    super(problem.detail || problem.title);
    this.name = 'ApiError';
  }
}

// ------------------------------------------------------------ administration

export interface SourceUpdate {
  host?: string;
  scope?: string;
  auth?: SourceAuth;
  refresh?: RefreshInterval;
}

export interface DiscoveryRequest {
  host?: string;
  scope?: string;
  auth: SourceAuth;
  displayName?: string;
}

export interface Discovery {
  connected: boolean;
  statusText: string;
  objects: { name: string; rows: number }[];
}

export type RoleName = 'owner' | 'builder' | 'governor' | 'member' | 'administrator' | 'auditor' | 'agent';

export interface Scope {
  kind: 'tenant' | 'company' | 'domain';
  companyId?: string | null;
  domainKey?: DomainKey | null;
  label: string;
}

export interface RoleAssignment {
  id: string;
  groupId?: string;
  role: RoleName;
  scope: Scope;
}

export interface User {
  id: string;
  name: string;
  email: string;
  department?: string | null;
  companyId?: string | null;
  companyName?: string | null;
  groups: { id: string; name: string }[];
  effectiveRoles: RoleAssignment[];
  lastLoginAt?: string | null;
}

export interface Group {
  id: string;
  name: string;
  description: string;
  validUntil?: string | null;
  memberCount: number;
  members?: User[];
  roles: RoleAssignment[];
}

export interface GroupInput {
  name: string;
  description?: string;
}

export interface RoleInfo {
  role: RoleName;
  label: string;
  description: string;
  assigned: number;
}

export interface RoleGroup {
  group: Group;
  scopes: Scope[];
}

export interface Agent {
  id: string;
  name: string;
  platform: string;
  companyId?: string | null;
  domainKey?: DomainKey | null;
  domainName?: string | null;
  owner: string;
  access: boolean;
  reads: number;
  costEur: number;
}

export interface CostSummary {
  month: string;
  measuredEur: number;
  allocatedEur: number;
  agentsRegistered: number;
  agentsWithAccess: number;
  reads: number;
  byPlatform: { platform: string; agentsWithAccess: number; costEur: number; sharePercent: number }[];
  /** Ontaix's own language model calls this month; separate from the agent figures. */
  llm?: LlmUsage;
}

export interface LlmUsage {
  calls: number;
  inputTokens: number;
  outputTokens: number;
  tokensUsed: number;
  tokenCap: number;
  costEur: number;
  byPurpose: { purpose: 'teach_extraction'; calls: number; costEur: number }[];
}

export interface CrossCompanyDisabled {
  removedRelations: number;
  rejectedProposals: number;
  proposal: Proposal;
  audit: AuditEntry;
  settings: Settings;
}

export interface RefreshAllResult {
  sources: number;
  bindings: number;
}
