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

export interface ConceptDraft {
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

export interface SpecDraft {
  type: 'spec';
  companyId: string;
  parentId: string;
  parentLabel?: string;
  label: string;
  rule?: string;
  domainKey: DomainKey;
  caption?: string;
}

export interface RelationDraft {
  type: 'relation';
  aId: string;
  bId: string;
  aLabel?: string;
  bLabel?: string;
  action: string;
  caption?: string;
}

export interface SourceDraft {
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

export interface BindingDraft {
  type: 'bind';
  sourceId: string;
  conceptIds: string[];
  caption?: string;
}

export interface AttributeDraft {
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
  | 'resolve_conflict';

export interface ChangeDraft {
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
  approvals: { ordinal: 1 | 2; userId: string; userName?: string; approvedAt: string }[];
  bulk?: boolean;
  createdAt: string;
  decidedAt?: string | null;
  artefacts?: Artefacts;
}

export interface AuditEntry {
  id: number;
  at: string;
  actor: Actor;
  kind: string;
  what: string;
  ok: boolean;
  proposalId?: string | null;
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

export interface FinaliseResult {
  companies: number;
  concepts: number;
  bound: number;
  equivalences: number;
  approved: number;
  scenesPlayed: number;
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
  demoStory: boolean;
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
  sceneIdx: number;
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
  demoStory: { enabled: boolean; sceneIdx?: number; sceneCount?: number };
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

export interface TeachResult {
  outcome: 'understood' | 'partly_understood' | 'not_understood' | 'scene';
  domainKey: DomainKey | null;
  intents: Intent[];
  drafts: ProposalDraft[];
  statements?: string[];
  caption: string;
  scene?: DemoScene | null;
}

export interface DemoScene {
  index: number;
  name: string;
  say: string;
  match: string;
}

export interface DemoScenes {
  sceneIdx: number;
  scenes: DemoScene[];
}

export interface DemoNext {
  sceneIdx: number;
  scene: DemoScene;
  proposals: Proposal[];
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
  ) {
    super(problem.detail || problem.title);
    this.name = 'ApiError';
  }
}
