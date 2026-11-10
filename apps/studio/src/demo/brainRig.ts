/**
 * The demo brain's rig, planned once the brain is: the data cores that stand under the brain and
 * the cables that plug them into it, the data run that lights the grown brain, and the agents that
 * work on it at the end. `brainRigLayer.ts` draws it.
 *
 * Cores: every example data source becomes a core in a row under the brain, sized to the brain
 * so it stays in proportion from afar. Its cable reaches up from its top and plugs into a socket
 * on the brain's underside. The first cores plug in as the camera pulls back, before the brain
 * grows; the others slide in from below while it grows and plug in one by one.
 *
 * Data run: once the brain has grown, light runs up the cables into one lobe after another; it
 * enters the lobe where the cable plugs in and spreads through it, each cell lighting up as it is
 * reached, then dimming to a soft glow. Then every cable carries light at once and the whole brain
 * lights up.
 *
 * Agents: one agent asks a question; its path lights up concept by concept across the domains,
 * through the company's own concepts where they carry the names it looks for, and the answer
 * comes back. It proposes a new concept, drawn dashed in gold until a person
 * approves it and it turns solid. Then the camera pulls back and more agents work on the brain at
 * the same time, two of them meeting on a shared concept where one hands over to the other.
 */
import type { Node } from '../canvas/types';
import type { BrainCell } from './brainDemo';
import { CORE_KEY } from './brainVocabulary';

export interface BrainCore {
  /** The source cell it carries. */
  source: number;
  /** Its centre x, top y, width and height, and the room between two cores, in world units. */
  x: number;
  top: number;
  w: number;
  h: number;
  pitch: number;
  /** Where its cable plugs into the brain's underside. */
  sx: number;
  sy: number;
  /** Points along its cable, from the core's top to the socket, and its three strands. */
  cable: [number, number][];
  strands: [number, number][][];
  /** When its cable starts reaching up and when it plugs in. */
  reachAt: number;
  plugAt: number;
  /** True for a core that slides in while the brain grows. */
  joins: boolean;
}

/** The data run's pass through one lobe. */
export interface BrainRun {
  domain: string;
  /** When light leaves the cores for it. */
  at: number;
  /** The cores whose cables carry it, and where the light enters the lobe. */
  cores: number[];
  entry: [number, number];
  /** The lobe's cells, and those a spark runs to from the entry. */
  cells: number[];
  sparks: number[];
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
  cores: BrainCore[];
  /** For each cell, when the data run lights it; Infinity for none. */
  litAt: Float64Array;
  runs: BrainRun[];
  /** When every cable carries light at once, and where the wave of light starts: the sockets' middle. */
  allAt: number;
  origin: [number, number];
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
  /** What the camera shows once pulled back: the brain, its cores and the agents. */
  frame: [number, number, number, number];
  /** When the whole rig has played. */
  end: number;
}

/**
 * Cores: share of the brain's width each is wide (at most CORE_FILL of the room between two),
 * height to width, distance under the brain in neighbour distances, and how much lower every
 * second one stands, in core heights plus the room for a name, so names never meet.
 */
const CORE_SHARE = 0.085;
const CORE_FILL = 0.75;
const CORE_TALL = 1.35;
const CORE_DROP = 3;
const CORE_STAGGER = 1.1;
/** Share of the brain's width kept free at each end of the row of cores. */
const CORE_INSET = 0.06;
/** How far the sockets lean in toward the middle, as a share of the core's distance from it, and the half-width of the strip the brain's underside is read from, in neighbour distances. */
const SOCKET_PULL = 0.85;
const SOCKET_BAND = 2.5;
/** A cable's width as a share of its core's, and the room under a core kept for its name, in core widths and at least in neighbour distances. */
export const CABLE_SHARE = 0.3;
const NAME_ROOM = 0.6;
const NAME_ROOM_MIN = 5;
/** Seconds a joining core takes to slide in, and a cable to reach up and plug in. */
export const SLIDE = 0.6;
export const PLUG = 0.7;
/** Data run: seconds after the brain has grown before it starts, between two lobes, for light to run up a cable, and to spread through a lobe; sparks into each lobe. */
const RUN_DELAY = 0.8;
const LOBE_STEP = 0.5;
export const CABLE_RUN = 0.55;
const SPREAD = 0.7;
const RUN_SPARKS = 16;
/** Seconds after the last lobe before every cable carries light, the wave of light's run, and the pause before the agents. */
const ALL_GAP = 0.4;
export const WAVE = 1.8;
const AGENT_GAP = 0.6;
/** Agents: their distance outside the brain, the room the camera keeps around each, and on a phone how much higher every second one stands, in neighbour distances. */
const AGENT_OUT = 3.5;
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
/** The proposal's distance outside the brain, in neighbour distances. */
const PROPOSAL_OUT = 2;
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

/** The agents, the first one asking the question; a route with a hand-off ends at the next agent. Its angle around the brain, in degrees. */
interface AgentSpec {
  name: string;
  angle: number;
  route: Stop[];
  handoff?: number;
}
const AGENTS: AgentSpec[] = [
  { name: 'Procurement agent', angle: -170, route: QUESTION_ROUTE },
  { name: 'Planning agent', angle: -132, route: [['production', 'Work order'], ['production', 'Production line'], ['production', 'Bill of materials']] },
  { name: 'Quality agent', angle: -92, route: [['quality', 'Inspection'], ['quality', 'Defect'], ['quality', 'Corrective action']] },
  {
    name: 'Sales agent',
    angle: -52,
    route: [['sales', 'Opportunity'], ['sales', 'Sales order'], ['sales', 'Customer'], ['maintenance', 'Service visit'], ['maintenance', 'Installed base']],
    handoff: 2,
  },
  { name: 'Service agent', angle: -12, route: [] },
  { name: 'Finance agent', angle: 24, route: [['finance', 'Invoice'], ['finance', 'Payment'], ['finance', 'Margin']] },
];
/** On a phone four agents stand in a row over the brain, where the screen has room. */
const AGENTS_SMALL: AgentSpec[] = [AGENTS[0], AGENTS[2], AGENTS[3], AGENTS[4]];

export interface RigPlan {
  cells: BrainCell[];
  /** The company's own concepts in the brain, each with its place. */
  joined: Map<Node, { x: number; y: number }>;
  /** Domain keys in lobe order. */
  domains: string[];
  box: [number, number, number, number];
  spacing: number;
  radius: number;
  small: boolean;
  /** When the first cores reach their places under the brain, and when the brain has grown. */
  arrive: number;
  grown: number;
}

/** The world points of a cubic curve from a to d, `n` steps. */
function curve(a: [number, number], b: [number, number], c: [number, number], d: [number, number], n: number): [number, number][] {
  const out: [number, number][] = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n,
      u = 1 - t;
    out.push([
      u * u * u * a[0] + 3 * u * u * t * b[0] + 3 * u * t * t * c[0] + t * t * t * d[0],
      u * u * u * a[1] + 3 * u * u * t * b[1] + 3 * u * t * t * c[1] + t * t * t * d[1],
    ]);
  }
  return out;
}

/** The line `off` to the side of a polyline, side by side with it all the way. */
function beside(line: [number, number][], off: number): [number, number][] {
  return line.map(([x, y], i) => {
    const [ax, ay] = line[Math.max(0, i - 1)],
      [bx, by] = line[Math.min(line.length - 1, i + 1)];
    const l = Math.hypot(bx - ax, by - ay) || 1;
    return [x + ((ay - by) / l) * off, y + ((bx - ax) / l) * off];
  });
}

/** Plans the rig of a brain whose cells are in birth order; sets the sources' places under the brain. */
export function planRig(p: RigPlan): BrainRig {
  const { cells, spacing, box } = p;
  const [x0, y0, x1, y1] = box;
  const bw = x1 - x0,
    bh = y1 - y0,
    cx = (x0 + x1) / 2,
    cy = (y0 + y1) / 2;
  const sources = cells.flatMap((c, i) => (c.story?.source ? [i] : []));
  const brain = cells.flatMap((c, i) => (c.story?.source ? [] : [i]));
  const frame: [number, number, number, number] = [x0, y0, x1, y1];
  const grow = (x: number, y: number, rx: number, ry: number) => {
    frame[0] = Math.min(frame[0], x - rx);
    frame[1] = Math.min(frame[1], y - ry);
    frame[2] = Math.max(frame[2], x + rx);
    frame[3] = Math.max(frame[3], y + ry);
  };

  // Cores: the first ones spread among the rest across the brain's width.
  const n = sources.length;
  const first = sources.filter((i) => cells[i].born < p.arrive);
  const slots = new Map<number, number>();
  first.forEach((i, k) => slots.set(i, first.length > 1 ? Math.round((k * (n - 1)) / (first.length - 1)) : Math.floor((n - 1) / 2)));
  const used = new Set(slots.values());
  let free = 0;
  for (const i of sources) {
    if (slots.has(i)) continue;
    while (used.has(free)) free++;
    slots.set(i, free);
    used.add(free);
  }
  const left = x0 + bw * CORE_INSET,
    right = x1 - bw * CORE_INSET;
  const pitch = n > 1 ? (right - left) / (n - 1) : bw;
  const w = Math.min(bw * CORE_SHARE, pitch * CORE_FILL),
    h = w * CORE_TALL,
    cw = w * CABLE_SHARE;
  const nameRoom = Math.max(w * NAME_ROOM, spacing * NAME_ROOM_MIN);
  const band = spacing * SOCKET_BAND;
  const underside = (x: number): number => {
    let y = -Infinity;
    for (const i of brain) if (Math.abs(cells[i].x - x) < band) y = Math.max(y, cells[i].y);
    return y === -Infinity ? cy : y + p.radius * 0.4;
  };
  const cores: BrainCore[] = sources.map((i) => {
    const j = slots.get(i) as number;
    const c = cells[i];
    const x = n > 1 ? left + pitch * j : cx;
    const top = y1 + spacing * CORE_DROP + (j % 2 ? h * CORE_STAGGER + nameRoom : 0);
    const sx = cx + (x - cx) * SOCKET_PULL,
      sy = underside(sx);
    const lift = top - sy;
    const cable = curve([x, top], [x, top - lift * 0.45], [sx, sy + lift * 0.45], [sx, sy], 28);
    const joins = !first.includes(i);
    const reachAt = joins ? c.born + SLIDE : p.arrive;
    c.x = c.px = x;
    c.y = c.py = top + h / 2;
    if (joins && c.story) Object.assign(c.story, { x: c.x, y: c.y });
    grow(x, top + h, Math.max(w, pitch), nameRoom);
    return { source: i, x, top, w, h, pitch, sx, sy, cable, strands: [-1, 0, 1].map((k) => beside(cable, k * cw * 0.32)), reachAt, plugAt: reachAt + PLUG, joins };
  });
  const origin: [number, number] = cores.length
    ? [cores.reduce((a, c) => a + c.sx, 0) / cores.length, cores.reduce((a, c) => a + c.sy, 0) / cores.length]
    : [cx, y1];

  // The data run: one lobe after another, the brain stem last.
  const litAt = new Float64Array(cells.length).fill(Infinity);
  const groups = new Map<string, number[]>();
  for (const i of brain) {
    const list = groups.get(cells[i].domain);
    if (list) list.push(i);
    else groups.set(cells[i].domain, [i]);
  }
  const order = [...p.domains.filter((k) => groups.has(k)), ...(groups.has(CORE_KEY) ? [CORE_KEY] : [])];
  const runAt = p.grown + RUN_DELAY;
  const runs: BrainRun[] = order.map((key, k) => {
    const list = groups.get(key) as number[];
    const mx = list.reduce((a, i) => a + cells[i].x, 0) / list.length,
      my = list.reduce((a, i) => a + cells[i].y, 0) / list.length;
    const near = cores
      .map((c, j) => [j, Math.hypot(c.sx - mx, c.sy - my)] as const)
      .sort((a, b) => a[1] - b[1])
      .map(([j]) => j)
      .slice(0, 2);
    const entry: [number, number] = near.length ? [cores[near[0]].sx, cores[near[0]].sy] : origin;
    const at = runAt + k * LOBE_STEP;
    const dist = list.map((i) => Math.hypot(cells[i].x - entry[0], cells[i].y - entry[1]));
    const far = Math.max(1, ...dist);
    list.forEach((i, m) => (litAt[i] = at + CABLE_RUN + (SPREAD * dist[m]) / far));
    const byDist = list.slice().sort((a, b) => litAt[a] - litAt[b]);
    const count = Math.min(RUN_SPARKS, byDist.length);
    const sparks = Array.from({ length: count }, (_, m) => byDist[Math.floor(((m + 0.5) * byDist.length) / count)]);
    return { domain: key, at, cores: near, entry, cells: list, sparks };
  });
  const allAt = runAt + order.length * LOBE_STEP + ALL_GAP;
  const agentAt = allAt + CABLE_RUN + WAVE + AGENT_GAP;

  // Agents stand around the brain. Each route's stops are the concepts it names: a demo cell or one
  // of the company's own concepts of that name, or failing that a cell of the same domain, or any.
  const norm = (t: string) => t.trim().toLowerCase().replace(/s$/, '');
  const ofCell = (i: number): RouteStop => ({ x: cells[i].x, y: cells[i].y, label: cells[i].label, color: cells[i].color, domain: cells[i].domain, cell: i });
  const own = [...p.joined].map(
    ([n, at]): RouteStop => ({ x: at.x, y: at.y, label: n.label, color: n.domain?.color ?? cells[brain[0]]?.color ?? '', domain: n.domain?.key ?? CORE_KEY, cell: -1 }),
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
        ? [x0 + (bw * (k + 0.5)) / specs.length, y0 - spacing * (AGENT_OUT + (k % 2 ? 0 : AGENT_STAGGER_SMALL))]
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
    const first = q.stops[0];
    routes.push({ from: 0, to: -1, stops: q.stops, handoff: -1, at: beamAt, period: 0 });
    question = {
      route: 0,
      ask: q.exact ? QUESTION : `How does ${first.label} affect ${q.stops[q.stops.length - 1].label}?`,
      answer: q.exact ? ANSWER : `${q.stops.length} concepts across ${new Set(q.stops.map((o) => o.domain)).size} domains connect them`,
      askAt,
      returnAt,
      answerAt,
    };

    // It proposes a new concept just outside the brain, beside the concept it started from.
    const propAt = answerAt + ANSWER_HOLD;
    let ux = first.x - cx,
      uy = first.y - cy;
    const ul = Math.hypot(ux, uy) || 1;
    ux /= ul;
    uy /= ul;
    let px = first.x,
      py = first.y;
    for (let k = 0; k < 120 && brain.some((i) => Math.hypot(cells[i].x - px, cells[i].y - py) < spacing * 1.2); k++) {
      px += ux * spacing * 0.5;
      py += uy * spacing * 0.5;
    }
    px += ux * spacing * PROPOSAL_OUT;
    py += uy * spacing * PROPOSAL_OUT;
    const approveAt = propAt + PROPOSE_DRAW + APPROVE_AFTER;
    proposal = { from: first, x: px, y: py, label: q.exact ? PROPOSAL : `${first.label} risk score`, color: first.color, at: propAt, approveAt };
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
    cores,
    litAt,
    runs,
    allAt,
    origin,
    agents,
    routes,
    question,
    proposal,
    agentAt,
    focusAt: agentAt - FOCUS_IN * 0.5,
    backAt,
    focus,
    frame,
    end: agents.length ? backAt + BACK + END_HOLD : allAt + CABLE_RUN + WAVE,
  };
}
