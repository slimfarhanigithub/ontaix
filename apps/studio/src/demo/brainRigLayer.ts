/**
 * Draws the demo brain's rig (`brainRig.ts`) over the brain: the sources' connections, the brain
 * firing, and the agents.
 *
 * Connections are drawn as the canvas draws a binding, the source colour at 0.5 opacity, each
 * reaching from its source to its cell in 0.5 s.
 *
 * Firing: light comes down from a source as a spark onto the lobe's landing cell, then fires
 * along the brain's relations and between neighbours, a short bright streak running to the next cell,
 * which flashes (a brighter copy of its sphere and a halo) and falls back. In the cascade every
 * source sends down all its connections at once. Once every cell has fired, one cell in three
 * twinkles now and then, each at its own pace, so the brain looks alive.
 *
 * Agents are drawn in the machine colour (`--link`), a proposal in gold until a person approves it
 * (`--human`), an approval in green (`--good`). An agent is a disc with a spark glyph and its name
 * over it; a spark runs from it along its route, each concept it reaches ringed and named. Agent
 * marks, names, bubbles and chips keep their size on screen. With reduced motion no spark runs or
 * twinkles: the cells light and fade in the same order, the concepts light up in turn; with Skip
 * animation the brain stands still and every agent stands with its route drawn.
 */
import { FONT_SANS, LIGHT_FALLBACK, themedColour, token } from '../design/tokens';
import { clamp, ease, hex } from '../canvas/colour';
import { roundRect } from '../canvas/labels';
import type { CanvasTheme } from '../canvas/themes';
import { LINK_DRAW, type BrainDemo } from './brainDemo';
import { AGENT_IN, CASCADE_HOP, DOWN, FIRE_HOP, HOP, HOP_TRAVEL, PROPOSE_DRAW, RETURN, type BrainRig, type BrainRoute, type RouteStop } from './brainRig';
import { drawGlow, drawSphere, Pulses } from './brainSprites';

/** The machine colour of agents and their sparks, as a stored (light) colour. */
const AGENT = LIGHT_FALLBACK['--link'];
/** Opacity and least width of a connection, as the canvas draws a binding. */
const LINK_ALPHA = 0.5;
const LINK_WIDTH = 1;
/** A firing cell: seconds it flashes, a firing streak's head and tail, its halo in cell radii, and how far ahead of its flash a streak starts, in relations. */
const FLASH = 0.7;
const FLASH_R = 3;
const STREAK_LEAD = 1.5;
/** Twinkling: one cell in TWINKLE_EVERY twinkles, how sharply (a higher power is a shorter twinkle), and its slowest and fastest pace in radians per second. */
const TWINKLE_EVERY = 3;
const TWINKLE_POWER = 18;
const TWINKLE_SLOW = 0.9;
const TWINKLE_FAST = 2.2;
/** Sparks a source sends down a connection in the cascade, one after another. */
const CASCADE_SPARKS = 3;
/** An agent's radius, a route's spark and line width, a ring's least radius and its line, in CSS pixels. */
const AGENT_PX = 12;
const SPARK_PX = 8;
const ROUTE_PX = 1.6;
const RING_PX = 8;
const RING_LINE_PX = 2;
/** Seconds a ring of a looping route fades over, and opacity of a route's line. */
const RING_FADE = 1.4;
const ROUTE_ALPHA = 0.4;
/** Text sizes in CSS pixels: a name, a bubble's caption and text, a chip; the bubble's widest and its padding. */
const LABEL_PX = 12;
const CAPTION_PX = 11;
const BUBBLE_PX = 13;
const BUBBLE_W = 280;
const PAD_PX = 9;
/** Seconds an approval's burst runs, and a hand-off chip shows. */
const BURST = 0.6;
const HANDOFF_SHOW = 1.6;

/** Words of `text` in lines no wider than `max`, at the context's font. */
function wrap(ctx: CanvasRenderingContext2D, text: string, max: number): string[] {
  const lines: string[] = [];
  let line = '';
  for (const word of text.split(' ')) {
    const next = line ? `${line} ${word}` : word;
    if (line && ctx.measureText(next).width > max) {
      lines.push(line);
      line = word;
    } else line = next;
  }
  if (line) lines.push(line);
  return lines;
}

/** A pill of text centred on x, baseline y: its fill, edge and text colours as rgba strings. */
function pill(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, size: number, zoom: number, fill: string, edge: string, ink: string): [number, number, number, number] {
  const w = ctx.measureText(text).width + 14 / zoom,
    h = size * 1.6;
  const box: [number, number, number, number] = [x - w / 2, y - size * 1.15, x + w / 2, y - size * 1.15 + h];
  roundRect(ctx, box[0], box[1], w, h, h / 2);
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.strokeStyle = edge;
  ctx.lineWidth = 1 / zoom;
  ctx.stroke();
  ctx.fillStyle = ink;
  ctx.fillText(text, x, y);
  return box;
}

/** The sources' connections into the brain: under the brain's cells. */
export function drawLinks(ctx: CanvasRenderingContext2D, d: BrainDemo, e: number, fade: number, zoom: number, hidden: Set<string>): void {
  const rig = d.rig;
  if (!rig) return;
  ctx.lineCap = 'round';
  ctx.lineWidth = Math.max(LINK_WIDTH, 0.9 / zoom);
  for (const s of rig.sources) {
    const src = d.cells[s.source];
    if (e < src.born) continue;
    const col = themedColour(src.color);
    for (const l of s.links) {
      if (e < l.at) break;
      const c = d.cells[l.cell];
      if (hidden.has(c.domain)) continue;
      const t = clamp((e - l.at) / LINK_DRAW, 0, 1);
      const q = d.reduced ? 1 : ease(t);
      ctx.strokeStyle = hex(col, LINK_ALPHA * fade * (d.reduced ? t : 1));
      ctx.beginPath();
      ctx.moveTo(src.x, src.y);
      ctx.lineTo(src.x + (c.x - src.x) * q, src.y + (c.y - src.y) * q);
      ctx.stroke();
    }
  }
}

/** How strongly a source sends after `e` seconds, 0 to 1: while its light comes down for a lobe or the cascade. */
export function sendingOf(rig: BrainRig, k: number, e: number): number {
  let v = 0;
  const bump = (t: number) => (t >= 0 && t <= DOWN * 2 ? 1 - Math.abs(t - DOWN) / DOWN : 0);
  for (const r of rig.runs) if (r.source === k) v = Math.max(v, bump(e - r.at + DOWN * 0.5));
  return Math.max(v, bump(e - rig.allAt + DOWN * 0.5));
}

/** The firing cell `i` of `at`/`from` adds to a frame `a` seconds after it fires: its streak along the relation it fires from, and its flash. */
function fire(ctx: CanvasRenderingContext2D, d: BrainDemo, pulses: Pulses, i: number, a: number, from: number, hop: number, fade: number, still: boolean): void {
  const c = d.cells[i];
  if (!still && from >= 0 && a < 0 && a >= -hop * STREAK_LEAD) {
    const p = d.cells[from];
    const q = 1 + a / (hop * STREAK_LEAD);
    pulses.add(c.color, c.color, p.x, p.y, c.x, c.y, q, fade);
  }
  if (a < 0 || a >= FLASH) return;
  const k = 1 - a / FLASH;
  drawGlow(ctx, c.color, c.x, c.y, d.radius * FLASH_R, k * fade);
  ctx.globalCompositeOperation = 'lighter';
  ctx.globalAlpha = Math.pow(k, 1.5) * fade;
  drawSphere(ctx, c.color, c.x, c.y, d.radius);
  ctx.globalAlpha = 1;
  ctx.globalCompositeOperation = 'source-over';
}

/** A cell's twinkle after `e` seconds, 0 to 1, each twinkling cell at its own pace. */
function twinkleOf(i: number, e: number): number {
  if (i % TWINKLE_EVERY) return 0;
  const h1 = ((i * 2654435761) >>> 0) / 4294967296,
    h2 = ((i * 40503 + 977) % 1009) / 1009;
  const v = Math.sin(e * (TWINKLE_SLOW + (TWINKLE_FAST - TWINKLE_SLOW) * h1) + h2 * 6.283);
  return v > 0 ? Math.pow(v, TWINKLE_POWER) : 0;
}

/** The brain firing and twinkling, over its cells. */
export function drawFiring(ctx: CanvasRenderingContext2D, d: BrainDemo, e: number, fade: number, zoom: number, hidden: Set<string>, inRect: (x: number, y: number) => boolean): void {
  const rig = d.rig;
  if (!rig || !rig.runs.length || e < rig.runs[0].at || fade <= 0) return;
  const still = d.reduced || d.instant;
  const pulses = new Pulses();
  // Light comes down from a source onto a lobe's landing cell, and in the cascade down every connection.
  if (!still) {
    for (const r of rig.runs) {
      const q = (e - r.at) / DOWN;
      if (q <= 0 || q >= 1 || hidden.has(r.domain)) continue;
      const s = d.cells[rig.sources[r.source].source],
        c = d.cells[r.landing];
      pulses.add(s.color, c.color, s.x, s.y, c.x, c.y, ease(q), fade, (SPARK_PX * 1.2) / zoom);
    }
    for (const src of rig.sources) {
      const s = d.cells[src.source];
      for (const l of src.links) {
        const c = d.cells[l.cell];
        if (hidden.has(c.domain)) continue;
        for (let k = 0; k < CASCADE_SPARKS; k++) {
          const q = (e - rig.allAt) / DOWN - k * 0.3;
          if (q > 0 && q < 1) pulses.add(s.color, c.color, s.x, s.y, c.x, c.y, ease(q), fade);
        }
      }
    }
  }
  const lobes = e < rig.allAt + DOWN;
  const cascade = e >= rig.allAt && e < rig.settledAt + FLASH;
  const twinkle = !still && e >= rig.allAt + DOWN;
  for (let i = 0; i < d.cells.length; i++) {
    const c = d.cells[i];
    if (c.story?.source || hidden.has(c.domain) || !inRect(c.x, c.y)) continue;
    if (lobes && Number.isFinite(rig.fireAt[i])) fire(ctx, d, pulses, i, e - rig.fireAt[i], rig.fireFrom[i], FIRE_HOP, fade, still);
    if (cascade) fire(ctx, d, pulses, i, e - rig.cascadeAt[i], rig.cascadeFrom[i], CASCADE_HOP, fade, still);
    if (twinkle && e >= rig.cascadeAt[i] + FLASH) {
      const k = twinkleOf(i, e);
      if (k > 0.04) {
        drawGlow(ctx, c.color, c.x, c.y, d.radius * FLASH_R, 0.7 * k * fade);
        ctx.globalCompositeOperation = 'lighter';
        ctx.globalAlpha = 0.6 * k * fade;
        drawSphere(ctx, c.color, c.x, c.y, d.radius);
        ctx.globalAlpha = 1;
        ctx.globalCompositeOperation = 'source-over';
      }
    }
  }
  pulses.drawStreaks(ctx, zoom);
  pulses.drawSparks(ctx, zoom);
}

/** The points of a route: its agent, its concepts, and the agent it hands over to. */
function pointsOf(rig: BrainRig, r: BrainRoute): [number, number][] {
  const a = rig.agents[r.from];
  return [[a.x, a.y], ...r.stops.map((o): [number, number] => [o.x, o.y]), ...(r.to >= 0 ? [[rig.agents[r.to].x, rig.agents[r.to].y] as [number, number]] : [])];
}

/** Where a route is after `e` seconds: seconds into its pass, and how many passes are done; null before it starts. */
function passOf(r: BrainRoute, e: number): [number, number] | null {
  const t = e - r.at;
  if (t < 0) return null;
  if (!r.period) return [t, 0];
  return [t % r.period, Math.floor(t / r.period)];
}

/** Seconds since a spark of the route last reached stop `j` (1 or more), or null. */
function sinceStop(r: BrainRoute, e: number, j: number): number | null {
  const p = passOf(r, e);
  if (!p) return null;
  const arrive = (j - 1) * HOP + HOP * HOP_TRAVEL;
  const a = p[0] - arrive;
  if (a >= 0) return a;
  return p[1] > 0 ? a + r.period : null;
}

/** The agents over the brain's cells: their routes, sparks, rings and names, the first agent's bubble and its proposal. */
export function drawAgents(
  ctx: CanvasRenderingContext2D,
  TH: CanvasTheme,
  d: BrainDemo,
  e: number,
  fade: number,
  zoom: number,
  hidden: Set<string>,
  view: [number, number, number, number],
): void {
  const rig = d.rig;
  if (!rig || fade <= 0) return;
  const still = d.reduced || d.instant;
  const pulses = new Pulses();

  const ink = (a: number) => `rgba(${TH.INK},${a})`;
  const surface = (a: number) => `rgba(${TH.CHIP},${a})`;
  const agent = token('--link');
  const shown = (o: RouteStop) => !hidden.has(o.domain);
  const size = LABEL_PX / zoom;
  const labels: [number, number, number, number][] = [];
  const free = (b: [number, number, number, number]) => !labels.some(([a, b2, c, dd]) => b[0] < c && b[2] > a && b[1] < dd && b[3] > b2);
  // Every agent's name is placed first, so no concept's name covers it.
  ctx.font = `700 ${size}px ${FONT_SANS}`;
  for (const a of rig.agents) {
    if (e < a.at) continue;
    const w = ctx.measureText(a.name).width + 14 / zoom;
    const y = a.y - AGENT_PX / zoom - 8 / zoom;
    labels.push([a.x - w / 2, y - size * 1.15, a.x + w / 2, y + size * 0.45]);
  }

  // Routes: their lines, their sparks, and a ring and a name on each concept a spark reaches.
  const rings: [RouteStop, number][] = [];
  const handoffs: [RouteStop, number][] = [];
  rig.routes.forEach((r) => {
    const p = passOf(r, e);
    if (!p) return;
    const once = !r.period;
    // The first agent's pass ends when the camera pulls back; its loop takes over from there.
    const gone = once ? clamp((e - rig.backAt) / 0.6, 0, 1) : 0;
    if (gone >= 1) return;
    const stops = pointsOf(rig, r);
    const vis = (1 - gone) * fade;
    ctx.strokeStyle = hex(agent, ROUTE_ALPHA * vis);
    ctx.lineWidth = ROUTE_PX / zoom;
    ctx.beginPath();
    for (let j = 1; j < stops.length; j++) {
      const reached = p[1] > 0 || still ? 1 : clamp((p[0] - (j - 1) * HOP) / (HOP * HOP_TRAVEL), 0, 1);
      if (reached <= 0) break;
      const [ax, ay] = stops[j - 1],
        [bx, by] = stops[j];
      ctx.moveTo(ax, ay);
      ctx.lineTo(ax + (bx - ax) * reached, ay + (by - ay) * reached);
    }
    ctx.stroke();
    if (!still) {
      const seg = Math.floor(p[0] / HOP);
      const f = (p[0] - seg * HOP) / (HOP * HOP_TRAVEL);
      if (seg + 1 < stops.length && f < 1) {
        const [ax, ay] = stops[seg],
          [bx, by] = stops[seg + 1];
        pulses.add(AGENT, AGENT, ax, ay, bx, by, ease(f), vis, SPARK_PX / zoom);
      }
    }
    r.stops.forEach((o, j) => {
      if (!shown(o)) return;
      const since = sinceStop(r, e, j + 1);
      if (since === null) return;
      const a = once || still ? 1 : Math.max(0, 1 - since / RING_FADE);
      if (a > 0.01) rings.push([o, a * vis]);
      if (j === r.handoff && since < HANDOFF_SHOW) handoffs.push([o, (1 - since / HANDOFF_SHOW) * vis]);
    });
  });
  // The answer runs back from the last concept to the first agent.
  const qn = rig.question;
  if (qn && !still) {
    const r = rig.routes[qn.route];
    const last = r.stops[r.stops.length - 1];
    const q = (e - qn.returnAt) / RETURN;
    if (last && q > 0 && q < 1) {
      const a = rig.agents[r.from];
      pulses.add(AGENT, AGENT, last.x, last.y, a.x, a.y, ease(q), fade, SPARK_PX / zoom);
    }
  }
  pulses.drawStreaks(ctx, zoom);
  pulses.drawSparks(ctx, zoom);

  for (const [c, a] of rings) {
    ctx.strokeStyle = hex(agent, a);
    ctx.lineWidth = RING_LINE_PX / zoom;
    ctx.beginPath();
    ctx.arc(c.x, c.y, Math.max(d.radius * 1.7, RING_PX / zoom), 0, 6.283);
    ctx.stroke();
  }

  // The proposal: a dashed gold link and cell, solid once approved.
  const pr = rig.proposal;
  const prVis = pr ? fade * (1 - clamp((e - rig.backAt - 1.2) / 0.8, 0, 1)) : 0;
  if (pr && e >= pr.at && shown(pr.from)) {
    const from = pr.from;
    const q = d.reduced ? 1 : ease(clamp((e - pr.at) / PROPOSE_DRAW, 0, 1));
    const approved = e >= pr.approveAt;
    const R = Math.max(d.radius * 1.8, 9 / zoom);
    ctx.lineWidth = 2 / zoom;
    ctx.strokeStyle = approved ? hex(themedColour(pr.color), 0.8 * fade) : hex(token('--human'), 0.9 * fade);
    ctx.setLineDash(approved ? [] : [6 / zoom, 4 / zoom]);
    ctx.beginPath();
    ctx.moveTo(from.x, from.y);
    ctx.lineTo(from.x + (pr.x - from.x) * q, from.y + (pr.y - from.y) * q);
    ctx.stroke();
    if (q >= 1) {
      if (approved) {
        drawGlow(ctx, pr.color, pr.x, pr.y, R * 3, 0.6 * fade);
        ctx.globalAlpha = fade;
        drawSphere(ctx, pr.color, pr.x, pr.y, R);
        ctx.globalAlpha = 1;
        const b = (e - pr.approveAt) / BURST;
        if (b < 1 && !still) {
          ctx.strokeStyle = hex(token('--good'), (1 - b) * fade);
          ctx.beginPath();
          ctx.arc(pr.x, pr.y, R * (1 + 2.2 * ease(b)), 0, 6.283);
          ctx.stroke();
        }
      } else {
        ctx.fillStyle = hex(token('--human-soft'), 0.95 * fade);
        ctx.lineDashOffset = still ? 0 : (-e * 14) / zoom;
        ctx.beginPath();
        ctx.arc(pr.x, pr.y, R, 0, 6.283);
        ctx.fill();
        ctx.stroke();
        ctx.lineDashOffset = 0;
      }
    }
    ctx.setLineDash([]);
  }

  ctx.textAlign = 'center';
  // Names of the concepts ringed, each only where it overlaps no name placed already.
  ctx.font = `600 ${size}px ${FONT_SANS}`;
  for (const [c, a] of rings) {
    const y = c.y - Math.max(d.radius * 1.7, RING_PX / zoom) - 6 / zoom;
    const w = ctx.measureText(c.label).width + 14 / zoom;
    const box: [number, number, number, number] = [c.x - w / 2, y - size * 1.15, c.x + w / 2, y + size * 0.45];
    if (!free(box)) continue;
    labels.push(box);
    pill(ctx, c.label, c.x, y, size, zoom, surface(0.94 * a), hex(agent, 0.5 * a), ink(0.92 * a));
  }
  for (const [c, a] of handoffs) {
    const y = c.y + Math.max(d.radius * 1.7, RING_PX / zoom) + 18 / zoom;
    ctx.font = `700 ${CAPTION_PX / zoom}px ${FONT_SANS}`;
    labels.push(pill(ctx, 'Hand-off', c.x, y, CAPTION_PX / zoom, zoom, hex(agent, 0.95 * a), hex(agent, a), surface(a)));
  }
  if (pr && e >= pr.at + PROPOSE_DRAW && prVis > 0.01 && shown(pr.from)) {
    const R = Math.max(d.radius * 1.8, 9 / zoom);
    ctx.font = `600 ${size}px ${FONT_SANS}`;
    labels.push(pill(ctx, pr.label, pr.x, pr.y - R - 8 / zoom, size, zoom, surface(0.96 * prVis), hex(token('--human'), 0.6 * prVis), ink(0.95 * prVis)));
    const approved = e >= pr.approveAt;
    const cs = CAPTION_PX / zoom;
    ctx.font = `700 ${cs}px ${FONT_SANS}`;
    const chip = approved ? '✓ Approved by the domain owner' : 'Proposal · waiting for approval';
    const fill = approved ? token('--good-soft') : token('--human-soft');
    const text = approved ? token('--good') : token('--human-text');
    labels.push(pill(ctx, chip, pr.x, pr.y + R + 8 / zoom + cs * 1.15, cs, zoom, hex(fill, prVis), hex(text, 0.6 * prVis), hex(text, prVis)));
  }

  // Agents: a disc with a spark glyph, its name over it.
  rig.agents.forEach((a) => {
    if (e < a.at) return;
    const q = still ? 1 : ease(clamp((e - a.at) / AGENT_IN, 0, 1));
    const alpha = q * fade;
    const r = (AGENT_PX / zoom) * (0.6 + 0.4 * q);
    drawGlow(ctx, AGENT, a.x, a.y, r * 3, 0.55 * alpha);
    ctx.globalAlpha = alpha;
    ctx.fillStyle = agent;
    ctx.beginPath();
    ctx.arc(a.x, a.y, r, 0, 6.283);
    ctx.fill();
    ctx.strokeStyle = surface(0.95);
    ctx.lineWidth = 2 / zoom;
    ctx.stroke();
    // The glyph: a four-pointed spark.
    const g = r * 0.62;
    ctx.fillStyle = surface(1);
    ctx.beginPath();
    ctx.moveTo(a.x, a.y - g);
    ctx.quadraticCurveTo(a.x, a.y, a.x + g, a.y);
    ctx.quadraticCurveTo(a.x, a.y, a.x, a.y + g);
    ctx.quadraticCurveTo(a.x, a.y, a.x - g, a.y);
    ctx.quadraticCurveTo(a.x, a.y, a.x, a.y - g);
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.font = `700 ${size}px ${FONT_SANS}`;
    pill(ctx, a.name, a.x, a.y - r - 8 / zoom, size, zoom, surface(0.95 * alpha), hex(agent, 0.55 * alpha), hex(agent, alpha));
  });

  // The first agent's bubble: what it asks, then its answer, then its proposal.
  if (qn && rig.agents.length && e >= qn.askAt && e < rig.backAt + 0.6) {
    const a = rig.agents[0];
    const alpha = fade * clamp((e - qn.askAt) / 0.3, 0, 1) * (1 - clamp((e - rig.backAt) / 0.6, 0, 1));
    const [caption, text, tone] =
      pr && e >= pr.at
        ? ['Proposes a new concept', pr.label, token('--human-text')]
        : e >= qn.answerAt
          ? ['Answers', qn.answer, agent]
          : ['Asks', qn.ask, agent];
    const pad = PAD_PX / zoom,
      ts = BUBBLE_PX / zoom,
      cs = CAPTION_PX / zoom;
    const maxW = Math.min(BUBBLE_W / zoom, (view[2] - view[0]) * 0.62);
    ctx.font = `500 ${ts}px ${FONT_SANS}`;
    const lines = wrap(ctx, text, maxW - 2 * pad);
    const widest = Math.max(...lines.map((l) => ctx.measureText(l).width));
    ctx.font = `700 ${cs}px ${FONT_SANS}`;
    const w = Math.max(widest, ctx.measureText(caption).width, 60 / zoom) + 2 * pad;
    const h = pad * 2 + cs * 1.4 + lines.length * ts * 1.3;
    const r = AGENT_PX / zoom;
    let x = a.x - r;
    const y = a.y - r - 8 / zoom - size * 1.6 - 8 / zoom - h;
    x = Math.max(view[0] + 12 / zoom, Math.min(x, view[2] - 12 / zoom - w));
    ctx.shadowColor = ink(0.14 * alpha);
    ctx.shadowBlur = 12 / zoom;
    roundRect(ctx, x, y, w, h, 10 / zoom);
    ctx.fillStyle = surface(0.97 * alpha);
    ctx.fill();
    ctx.shadowBlur = 0;
    ctx.strokeStyle = hex(tone, 0.5 * alpha);
    ctx.lineWidth = 1 / zoom;
    ctx.stroke();
    ctx.textAlign = 'left';
    ctx.font = `700 ${cs}px ${FONT_SANS}`;
    ctx.fillStyle = hex(tone, alpha);
    ctx.fillText(caption, x + pad, y + pad + cs);
    ctx.font = `500 ${ts}px ${FONT_SANS}`;
    ctx.fillStyle = ink(0.92 * alpha);
    lines.forEach((l, k) => ctx.fillText(l, x + pad, y + pad + cs * 1.4 + ts * (1 + k * 1.3)));
    ctx.textAlign = 'center';
  }
}
