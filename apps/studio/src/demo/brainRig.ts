/**
 * The demo brain's rig, planned once the brain is: the sources over the brain and their
 * connections into it, the brain firing once grown, and the agents that work on it at the end.
 * `brainRigLayer.ts` draws it.
 *
 * Sources: once the camera pulls back, the example data sources stand in a row over the brain,
 * every second one a little higher so names never meet. Each connects to the brain cells nearest
 * it with thin mapping lines, one after another, each drawn once its cell has budded. The first
 * sources take their places as the camera pulls back; the others join the row while the brain
 * grows and connect the same way.
 *
 * Firing: once the brain has grown, light comes down from a source into one lobe after another
 * and fires through the lobe along the brain's relations and between neighbouring cells, each cell flashing as
 * it fires. Then every source sends at once and the whole brain fires in a cascade, from every
 * cell the sources connect to; then it twinkles, a few cells at a time glowing and fading.
 *
 * Agents: one agent asks a question; its path lights up concept by concept across the domains,
 * through the company's own concepts where they carry the names it looks for, and the answer
 * comes back. It proposes a new concept, drawn dashed in gold until a person approves it and it
 * turns solid. Then the camera pulls back and more agents work on the brain at the same time, two
 * of them meeting on a shared concept where one hands over to the other.
 */
import type { Node } from '../canvas/types';
import type { BrainCell, BrainLink } from './brainDemo';
import { CORE_KEY } from './brainVocabulary';

/** A source's place over the brain and its connections into it. */
export interface BrainSource {
  /** The source cell. */
  source: number;
  /** The brain cells it connects to, and when each connection starts to draw. */
  links: { cell: number; at: number }[];
  /** The widest its name may stand over it, in world units: two sources' room, its neighbours in its row being two sources away. */
  nameWidth: number;
  /** True for a source that joins while the brain grows. */
  joins: boolean;
}

/** One lobe's turn to fire: the source the light comes down from, and the cell it lands on. */
export interface BrainRun {
  domain: string;
  /** When the light leaves the source. */
  at: number;
  source: number;
  landing: number;
}

export interface BrainAgent {
  name: string;
  x: number;
  y: number;
  /** When it appears. */
  at: number;
}

/** A concept an agent's route reaches: a demo cell, or one of the company's own concepts at its place in the brain (cell -1). */
export interface RouteStop {
  x: number;
  y: number;
  label: string;
  color: string;
  domain: string;
  cell: number;
}

/** An agent's way through the brain: a spark runs from the agent from stop to stop. */
export interface BrainRoute {
  /** The agent it leaves from, and the agent it hands over to at its end, or -1. */
  from: number;
  to: number;
  stops: RouteStop[];
  /** Index in `stops` of the shared concept where one agent hands over to the other, or -1. */
  handoff: number;
  /** When the first spark leaves, and the loop's period, or 0 for one pass. */
  at: number;
  period: number;
}

/** The first agent's question: its route, what it asks and answers, and when. */
export interface BrainQuestion {
  route: number;
  ask: string;
  answer: string;
  askAt: number;
  /** When the answer leaves the last concept for the agent, and when the agent shows it. */
  returnAt: number;
  answerAt: number;
}

/** The concept the first agent proposes, beside the concept it starts from. */
export interface BrainProposal {
  from: RouteStop;
  x: number;
  y: number;
  label: string;
  color: string;
  /** When the agent proposes it, and when a person approves it. */
  at: number;
  approveAt: number;
}

export interface BrainRig {
  sources: BrainSource[];
  /** For each cell: when its lobe's turn fires it and the cell the firing comes from (-1 for the landing cell or none); Infinity when it never fires. */
  fireAt: Float64Array;
  fireFrom: Int32Array;
  runs: BrainRun[];
  /** When every source sends at once, and for each cell when the cascade fires it and the cell it comes from. */
  allAt: number;
  cascadeAt: Float64Array;
  cascadeFrom: Int32Array;
  /** When the cascade has fired every cell: the brain twinkles from then. */
  settledAt: number;
  agents: BrainAgent[];
  routes: BrainRoute[];
  question: BrainQuestion | null;
  proposal: BrainProposal | null;
  /** When the first agent appears, when the camera closes in on it, and when it pulls back to every agent. */
  agentAt: number;
  focusAt: number;
  backAt: number;
  /** What the camera shows while the first agent works. */
  focus: [number, number, number, number];
  /** What the camera shows once pulled back: the brain, the sources over it and the agents. */
  frame: [number, number, number, number];
  /** When the whole rig has played. */
  end: number;
}

/**
 * Sources over the brain: share of the brain's width kept free at each end of their row, their
 * distance over the brain's highest cell, how much higher every second one stands, and the room
 * kept over each for its name, in neighbour distances.
 */
const SOURCE_INSET = 0.06;
const SOURCE_ABOVE = 6;
const SOURCE_STAGGER = 3;
const SOURCE_STAGGER_SMALL = 8;
const SOURCE_NAME_ROOM = 4;
/** Connections each source makes, seconds after a source is in place before its first one and between two, and the least time after its cell buds. */
const SOURCE_LINKS = 6;
export const LINK_LEAD = 0.35;
const LINK_GAP = 0.12;
const LINK_AFTER_BUD = 0.2;
/** Firing: seconds after the brain has grown before it starts, between two lobes, for the light to come down from its source, and between two cells it fires along a relation; the same for the cascade. */
const FIRE_DELAY = 0.8;
const LOBE_STEP = 0.5;
export const DOWN = 0.5;
export const FIRE_HOP = 0.07;
const CASCADE_GAP = 0.6;
export const CASCADE_HOP = 0.045;
/** Cells this close, in neighbour distances, are neighbours firing can run between. */
const NEIGHBOUR = 1.8;
/** Seconds after the cascade before the first agent appears. */
const AGENT_GAP = 0.8;
/** Agents: their distance outside the brain, the room the camera keeps around each, and on a phone how much lower every second one stands, in neighbour distances. */
const AGENT_OUT = 4.5;
const AGENT_ROOM = 4;
const AGENT_STAGGER_SMALL = 9;
/** Seconds an agent takes to appear, and from appearing to its first spark. */
export const AGENT_IN = 0.5;
const ASK = 1.0;
/** Seconds between two stops of a route; a spark travels HOP_TRAVEL of it. */
export const HOP = 0.55;
export const HOP_TRAVEL = 0.8;
/** Seconds the answer takes back to the agent, and the answer shows before the proposal. */
export const RETURN = 0.6;
const ANSWER_HOLD = 1.4;
/** Seconds the proposal's link takes to draw, before a person approves it, and the approval shows. */
export const PROPOSE_DRAW = 0.5;
const APPROVE_AFTER = 1.6;
const APPROVED_HOLD = 1.4;
/** The proposal's distance outside the brain, in neighbour distances, and how far above level its way out may lean, in degrees, so it never stands among the sources. */
const PROPOSAL_OUT = 2.5;
const PROPOSAL_UP = 10;
/** The half-width of the strip along its way out read for the brain's edge, in neighbour distances, so a groove does not count as outside. */
const PROPOSAL_CLEAR = 1.6;
/** Seconds the camera takes to close in and to pull back, the gap between two agents appearing, a loop's pause, and the time held at the end. */
export const FOCUS_IN = 1.4;
export const BACK = 1.6;
const AGENT_STAGGER = 0.3;
const LOOP_PAUSE = 0.9;
const END_HOLD = 2.0;

/** A route stop: a domain key and the concept name it looks for there. */
type Stop = [string, string];

const QUESTION_ROUTE: Stop[] = [
  ['supply', 'Supplier'],
  ['supply', 'Purchase order'],
  ['supply', 'Goods receipt'],
  ['logistics', 'Delivery'],
  ['sales', 'Customer'],
];
const QUESTION = 'Which suppliers delay our deliveries to customers?';
const ANSWER = '3 suppliers · 41 late deliveries · 12 customers affected';
const PROPOSAL = 'Supplier risk score';

/** The agents, the first one asking the question; a route with a hand-off ends at the next agent. Its angle around the brain, in degrees, clockwise from the right: they stand beside and under it, the sources being over it. */
interface AgentSpec {
  name: string;
  angle: number;
  route: Stop[];
  handoff?: number;
}
const AGENTS: AgentSpec[] = [
  { name: 'Procurement agent', angle: 180, route: QUESTION_ROUTE },
  { name: 'Planning agent', angle: 148, route: [['production', 'Work order'], ['production', 'Production line'], ['production', 'Bill of materials']] },
  { name: 'Quality agent', angle: 118, route: [['quality', 'Inspection'], ['quality', 'Defect'], ['quality', 'Corrective action']] },
  {
    name: 'Sales agent',
    angle: 62,
    route: [['sales', 'Opportunity'], ['sales', 'Sales order'], ['sales', 'Customer'], ['maintenance', 'Service visit'], ['maintenance', 'Installed base']],
    handoff: 2,
  },
  { name: 'Service agent', angle: 30, route: [] },
  { name: 'Finance agent', angle: 0, route: [['finance', 'Invoice'], ['finance', 'Payment'], ['finance', 'Margin']] },
];
/** On a phone four agents stand in a row under the brain, where the screen has room. */
const AGENTS_SMALL: AgentSpec[] = [AGENTS[0], AGENTS[2], AGENTS[3], AGENTS[4]];

export interface RigPlan {
  cells: BrainCell[];
  links: BrainLink[];
  /** The company's own concepts in the brain, each with its place. */
  joined: Map<Node, { x: number; y: number }>;
  /** Domain keys in lobe order. */
  domains: string[];
  box: [number, number, number, number];
  spacing: number;
  small: boolean;
  /** When the first sources reach their places over the brain, and when the brain has grown. */
  arrive: number;
  grown: number;
}

/**
 * When each cell fires, spreading from `starts` along `near` one relation every `hop` seconds,
 * only through cells `ok` lets in, and the cell each fires from. Cells no relation reaches fire by
 * their distance from the nearest start, as if the firing ran on at its pace.
 */
function spread(
  cells: BrainCell[],
  near: number[][],
  starts: [number, number][],
  hop: number,
  ok: (i: number) => boolean,
  at: Float64Array,
  from: Int32Array,
  spacing: number,
): number {
  let queue: number[] = [];
  for (const [i, t] of starts)
    if (t < at[i]) {
      at[i] = t;
      from[i] = -1;
      queue.push(i);
    }
  queue.sort((a, b) => at[a] - at[b]);
  let last = 0;
  while (queue.length) {
    const next: number[] = [];
    for (const i of queue) {
      last = Math.max(last, at[i]);
      for (const j of near[i]) {
        if (!ok(j) || at[j] <= at[i] + hop) continue;
        at[j] = at[i] + hop;
        from[j] = i;
        next.push(j);
      }
    }
    queue = next;
  }
  // A cell no relation reaches fires as the firing would reach it across the gap.
  cells.forEach((c, i) => {
    if (!ok(i) || Number.isFinite(at[i])) return;
    let best = Infinity;
    for (const [s, t] of starts) best = Math.min(best, t + (hop * Math.hypot(c.x - cells[s].x, c.y - cells[s].y)) / spacing);
    at[i] = best;
    from[i] = -1;
    last = Math.max(last, best);
  });
  return last;
}

/** Plans the rig of a brain whose cells are in birth order; sets the sources' places over the brain. */
export function planRig(p: RigPlan): BrainRig {
  const { cells, spacing, box } = p;
  const [x0, y0, x1, y1] = box;
  const bw = x1 - x0,
    bh = y1 - y0,
    cx = (x0 + x1) / 2,
    cy = (y0 + y1) / 2;
  const sourceIdx = cells.flatMap((c, i) => (c.story?.source ? [i] : []));
  const brain = cells.flatMap((c, i) => (c.story?.source ? [] : [i]));
  const frame: [number, number, number, number] = [x0, y0, x1, y1];
  const grow = (x: number, y: number, rx: number, ry: number) => {
    frame[0] = Math.min(frame[0], x - rx);
    frame[1] = Math.min(frame[1], y - ry);
    frame[2] = Math.max(frame[2], x + rx);
    frame[3] = Math.max(frame[3], y + ry);
  };

  // Sources: the first ones spread among the rest across the brain's width, over it.
  const n = sourceIdx.length;
  const first = sourceIdx.filter((i) => cells[i].born < p.arrive);
  const slots = new Map<number, number>();
  first.forEach((i, k) => slots.set(i, first.length > 1 ? Math.round((k * (n - 1)) / (first.length - 1)) : Math.floor((n - 1) / 2)));
  const used = new Set(slots.values());
  let free = 0;
  for (const i of sourceIdx) {
    if (slots.has(i)) continue;
    while (used.has(free)) free++;
    slots.set(i, free);
    used.add(free);
  }
  const left = x0 + bw * SOURCE_INSET,
    right = x1 - bw * SOURCE_INSET;
  const pitch = n > 1 ? (right - left) / (n - 1) : bw;
  const sources: BrainSource[] = sourceIdx.map((i) => {
    const j = slots.get(i) as number;
    const c = cells[i];
    c.x = c.px = n > 1 ? left + pitch * j : cx;
    c.y = c.py = y0 - spacing * (SOURCE_ABOVE + (j % 2) * (p.small ? SOURCE_STAGGER_SMALL : SOURCE_STAGGER));
    const joins = !first.includes(i);
    if (joins && c.story) Object.assign(c.story, { x: c.x, y: c.y });
    grow(c.x, c.y, pitch / 2, spacing * SOURCE_NAME_ROOM);
    // Its connections: the brain cells nearest it, each once it has budded.
    const ready = (joins ? c.born : p.arrive) + LINK_LEAD;
    const nearest = brain
      .map((k) => [k, Math.hypot(cells[k].x - c.x, cells[k].y - c.y)] as const)
      .sort((a, b) => a[1] - b[1])
      .slice(0, SOURCE_LINKS)
      .map(([k]) => k);
    const links = nearest.map((k, m) => ({ cell: k, at: Math.max(ready + m * LINK_GAP, cells[k].born + LINK_AFTER_BUD) }));
    return { source: i, links: links.sort((a, b) => a.at - b.at), nameWidth: pitch * 1.8, joins };
  });

  // The ways firing runs, both ways: each cell's birth link to the cell it budded from, the further
  // relations, and the brain's neighbouring cells, so every lobe holds together.
  const at = new Map<string, number>();
  for (const i of brain) at.set(`${cells[i].x},${cells[i].y}`, i);
  const near: number[][] = cells.map(() => []);
  const join = (a: number, b: number) => {
    near[a].push(b);
    near[b].push(a);
  };
  for (const i of brain) {
    if (!cells[i].linked) continue;
    const parent = at.get(`${cells[i].px},${cells[i].py}`);
    if (parent !== undefined && parent !== i) join(i, parent);
  }
  for (const [a, b] of p.links) if (!cells[a].story?.source && !cells[b].story?.source) join(a, b);
  const reach = spacing * NEIGHBOUR;
  const grid = new Map<string, number[]>();
  const key = (x: number, y: number) => `${Math.floor(x / reach)},${Math.floor(y / reach)}`;
  for (const i of brain) {
    const k = key(cells[i].x, cells[i].y);
    const list = grid.get(k);
    if (list) list.push(i);
    else grid.set(k, [i]);
  }
  for (const i of brain) {
    const gx = Math.floor(cells[i].x / reach),
      gy = Math.floor(cells[i].y / reach);
    for (let dx = -1; dx <= 1; dx++)
      for (let dy = -1; dy <= 1; dy++)
        for (const j of grid.get(`${gx + dx},${gy + dy}`) ?? [])
          if (j > i && Math.hypot(cells[j].x - cells[i].x, cells[j].y - cells[i].y) <= reach) join(i, j);
  }

  // Firing: one lobe after another, the brain stem last, each from the cell of the lobe nearest a source.
  const fireAt = new Float64Array(cells.length).fill(Infinity);
  const fireFrom = new Int32Array(cells.length).fill(-1);
  const groups = new Map<string, number[]>();
  for (const i of brain) {
    const list = groups.get(cells[i].domain);
    if (list) list.push(i);
    else groups.set(cells[i].domain, [i]);
  }
  const order = [...p.domains.filter((k) => groups.has(k)), ...(groups.has(CORE_KEY) ? [CORE_KEY] : [])];
  const fireStart = p.grown + FIRE_DELAY;
  let fired = fireStart;
  const runs: BrainRun[] = sources.length
    ? order.map((key, k) => {
        const list = groups.get(key) as number[];
        let landing = list[0],
          source = 0,
          bd = Infinity;
        for (const i of list)
          sources.forEach((s, j) => {
            const dd = Math.hypot(cells[i].x - cells[s.source].x, cells[i].y - cells[s.source].y);
            if (dd < bd) {
              bd = dd;
              landing = i;
              source = j;
            }
          });
        const t = fireStart + k * LOBE_STEP;
        fired = Math.max(fired, spread(cells, near, [[landing, t + DOWN]], FIRE_HOP, (i) => cells[i].domain === key, fireAt, fireFrom, spacing));
        return { domain: key, at: t, source, landing };
      })
    : [];

  // The cascade: every source sends at once, the whole brain fires from every cell they connect to.
  const allAt = fired + CASCADE_GAP;
  const cascadeAt = new Float64Array(cells.length).fill(Infinity);
  const cascadeFrom = new Int32Array(cells.length).fill(-1);
  const starts: [number, number][] = sources.flatMap((s) => s.links.map((l): [number, number] => [l.cell, allAt + DOWN]));
  const settledAt = starts.length ? spread(cells, near, starts, CASCADE_HOP, (i) => !cells[i].story?.source, cascadeAt, cascadeFrom, spacing) : allAt;
  const agentAt = settledAt + AGENT_GAP;

  // Agents stand beside and under the brain. Each route's stops are the concepts it names: a demo
  // cell or one of the company's own concepts of that name, or failing that a cell of the same
  // domain, or any.
  const norm = (t: string) => t.trim().toLowerCase().replace(/s$/, '');
  const ofCell = (i: number): RouteStop => ({ x: cells[i].x, y: cells[i].y, label: cells[i].label, color: cells[i].color, domain: cells[i].domain, cell: i });
  const own = [...p.joined].map(
    ([node, place]): RouteStop => ({ x: place.x, y: place.y, label: node.label, color: node.domain?.color ?? cells[brain[0]]?.color ?? '', domain: node.domain?.key ?? CORE_KEY, cell: -1 }),
  );
  const pick = (stops: Stop[]): { stops: RouteStop[]; exact: boolean } => {
    const out: RouteStop[] = [];
    const taken = (x: number, y: number) => out.some((o) => o.x === x && o.y === y);
    let exact = true;
    for (const [key, label] of stops) {
      const want = norm(label);
      const i = brain.find((j) => norm(cells[j].label) === want && !taken(cells[j].x, cells[j].y));
      const mine = i === undefined ? own.find((o) => norm(o.label) === want && !taken(o.x, o.y)) : undefined;
      if (i !== undefined) out.push(ofCell(i));
      else if (mine) out.push(mine);
      else {
        exact = false;
        const k =
          brain.find((j) => cells[j].domain === key && !taken(cells[j].x, cells[j].y)) ??
          brain.find((j, m) => m >= ((out.length + 1) * brain.length) / (stops.length + 1) && !taken(cells[j].x, cells[j].y));
        if (k !== undefined) out.push(ofCell(k));
      }
    }
    return { stops: out, exact };
  };
  const specs = p.small ? AGENTS_SMALL : AGENTS;
  const rx = bw / 2 + spacing * AGENT_OUT,
    ry = bh / 2 + spacing * AGENT_OUT;
  const agents: BrainAgent[] = [];
  const routes: BrainRoute[] = [];
  let question: BrainQuestion | null = null;
  let proposal: BrainProposal | null = null;
  let backAt = agentAt;
  if (brain.length) {
    specs.forEach((sp, k) => {
      const [x, y] = p.small
        ? [x0 + (bw * (k + 0.5)) / specs.length, y1 + spacing * (AGENT_OUT + (k % 2 ? AGENT_STAGGER_SMALL : 0))]
        : [cx + Math.cos((sp.angle * Math.PI) / 180) * rx, cy + Math.sin((sp.angle * Math.PI) / 180) * ry];
      agents.push({ name: sp.name, x, y, at: agentAt });
    });
    for (const a of agents) grow(a.x, a.y, spacing * AGENT_ROOM, spacing * AGENT_ROOM);

    // The first agent's question, one pass out and the answer back.
    const q = pick(specs[0].route);
    const askAt = agentAt + AGENT_IN * 0.6;
    const beamAt = agentAt + ASK;
    const returnAt = beamAt + q.stops.length * HOP;
    const answerAt = returnAt + RETURN;
    const firstStop = q.stops[0];
    routes.push({ from: 0, to: -1, stops: q.stops, handoff: -1, at: beamAt, period: 0 });
    question = {
      route: 0,
      ask: q.exact ? QUESTION : `How does ${firstStop.label} affect ${q.stops[q.stops.length - 1].label}?`,
      answer: q.exact ? ANSWER : `${q.stops.length} concepts across ${new Set(q.stops.map((o) => o.domain)).size} domains connect them`,
      askAt,
      returnAt,
      answerAt,
    };

    // It proposes a new concept just outside the brain, beside the concept it started from: out
    // the shortest way across the brain's edge that does not lead up among the sources.
    const propAt = answerAt + ANSWER_HOLD;
    let px = firstStop.x,
      py = firstStop.y,
      best = Infinity;
    for (let deg = -PROPOSAL_UP; deg <= 180 + PROPOSAL_UP; deg += 10) {
      const ux = Math.cos((deg * Math.PI) / 180),
        uy = Math.sin((deg * Math.PI) / 180);
      // How far along this way the brain reaches.
      let reach = 0;
      for (const i of brain) {
        const vx = cells[i].x - firstStop.x,
          vy = cells[i].y - firstStop.y;
        const along = vx * ux + vy * uy;
        if (along > reach && Math.abs(vx * uy - vy * ux) < spacing * PROPOSAL_CLEAR) reach = along;
      }
      if (reach < best) {
        best = reach;
        px = firstStop.x + ux * (reach + spacing * PROPOSAL_OUT);
        py = firstStop.y + uy * (reach + spacing * PROPOSAL_OUT);
      }
    }
    const approveAt = propAt + PROPOSE_DRAW + APPROVE_AFTER;
    proposal = { from: firstStop, x: px, y: py, label: q.exact ? PROPOSAL : `${firstStop.label} risk score`, color: firstStop.color, at: propAt, approveAt };
    grow(px, py, spacing * AGENT_ROOM, spacing * AGENT_ROOM);
    backAt = approveAt + APPROVED_HOLD;

    // Then every agent works on the brain at once, again and again.
    specs.forEach((sp, k) => {
      if (k) agents[k].at = backAt + AGENT_IN + (k - 1) * AGENT_STAGGER;
      if (!sp.route.length) return;
      const r = k ? pick(sp.route) : q;
      const to = sp.handoff !== undefined && k + 1 < agents.length ? k + 1 : -1;
      const stops = r.stops.length + (to >= 0 ? 1 : 0);
      routes.push({
        from: k,
        to,
        stops: r.stops,
        handoff: to >= 0 ? (sp.handoff as number) : -1,
        at: (k ? agents[k].at + AGENT_IN : backAt + AGENT_IN) + (k % 3) * 0.35,
        period: stops * HOP + LOOP_PAUSE,
      });
    });
  }

  // While the first agent works, the camera closes in on it, its route and its proposal.
  const focus: [number, number, number, number] = [Infinity, Infinity, -Infinity, -Infinity];
  const add = (x: number, y: number, r: number) => {
    focus[0] = Math.min(focus[0], x - r);
    focus[1] = Math.min(focus[1], y - r);
    focus[2] = Math.max(focus[2], x + r);
    focus[3] = Math.max(focus[3], y + r);
  };
  if (agents.length) {
    add(agents[0].x, agents[0].y, spacing * AGENT_ROOM);
    for (const o of routes[0].stops) add(o.x, o.y, spacing * 3);
    if (proposal) add(proposal.x, proposal.y, spacing * AGENT_ROOM);
  } else focus.splice(0, 4, ...frame);

  return {
    sources,
    fireAt,
    fireFrom,
    runs,
    allAt,
    cascadeAt,
    cascadeFrom,
    settledAt,
    agents,
    routes,
    question,
    proposal,
    agentAt,
    focusAt: agentAt - FOCUS_IN * 0.5,
    backAt,
    focus,
    frame,
    end: agents.length ? backAt + BACK + END_HOLD : settledAt,
  };
}
