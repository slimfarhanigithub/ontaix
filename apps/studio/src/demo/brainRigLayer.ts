/**
 * Draws the demo brain's rig (`brainRig.ts`).
 *
 * Cores are drawn in world units, so they stay in proportion with the brain from afar: a dark
 * tower in the source colour with four lit slots and a port on top, its name under it. A story
 * source grows into its core as it flies to its place under the brain; a joining core slides up
 * into place. Its cable, three strands side by side around a lit line, reaches up from the port
 * and plugs into the brain's underside, where its connector flashes once and stays lit.
 *
 * The data run: sparks run up the cables carrying a lobe, enter the lobe and spread through it,
 * each cell flashing as the light reaches it, then glowing softly; then every cable carries light
 * at once and the finale's wave lights the whole brain (`brainLayer.ts`).
 *
 * Agents are drawn in the machine colour (`--link`), a proposal in gold until a person approves it
 * (`--human`), an approval in green (`--good`). An agent is a disc with a spark glyph and its name
 * over it; a spark runs from it along its route, each concept it reaches ringed and named. Agent
 * marks, names, bubbles and chips keep their size on screen. With reduced motion no spark runs:
 * the concepts light up in turn; with Skip animation every agent stands at its route at once.
 */
import { FONT_SANS, LIGHT_FALLBACK, MIX_BLACK, MIX_WHITE, themedColour, token } from '../design/tokens';
import { clamp, ease, hex, mix } from '../canvas/colour';
import { roundRect } from '../canvas/labels';
import type { CanvasTheme } from '../canvas/themes';
import { migration, type BrainDemo } from './brainDemo';
import { AGENT_IN, CABLE_RUN, CABLE_SHARE, HOP, HOP_TRAVEL, PLUG, PROPOSE_DRAW, RETURN, SLIDE, WAVE, type BrainCore, type BrainRig, type BrainRoute, type RouteStop } from './brainRig';
import { drawGlow, drawSphere, Pulses } from './brainSprites';

/** The machine colour of agents and their sparks, as a stored (light) colour. */
const AGENT = LIGHT_FALLBACK['--link'];
/** A story source's radius beside the company, and its smallest radius on screen in CSS pixels. */
const TILE_PX = 16;
/** A core's name: its size in core widths, at least NAME_PX on screen. */
const NAME_SHARE = 0.17;
const NAME_PX = 11;
/** How long a plugged connector flashes, and its steady glow. */
const PLUG_FLASH = 0.7;
const PLUG_GLOW = 0.35;
/** A lit cell: seconds it takes to light, then to dim to its rest, its rest, its halo in cell radii, and how long it flashes over its sphere. */
const LIT_RISE = 0.2;
const LIT_FALL = 1.0;
const LIT_REST = 0.4;
const LIT_R = 4;
const LIT_FLASH = 0.9;
/** Sparks per cable while every cable carries light, and how long their stream lasts in cable runs. */
const ALL_SPARKS = 5;
const ALL_STREAM = 2;
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

/** The point `q` of the way along a polyline, by its points. */
function pointAt(line: [number, number][], q: number): [number, number] {
  const f = clamp(q, 0, 1) * (line.length - 1);
  const k = Math.min(line.length - 2, Math.floor(f));
  const u = f - k;
  return [line[k][0] + (line[k + 1][0] - line[k][0]) * u, line[k][1] + (line[k + 1][1] - line[k][1]) * u];
}

/** Strokes the first `q` of a polyline. */
function strokePart(ctx: CanvasRenderingContext2D, line: [number, number][], q: number): void {
  const f = clamp(q, 0, 1) * (line.length - 1);
  ctx.beginPath();
  ctx.moveTo(line[0][0], line[0][1]);
  for (let k = 1; k <= Math.floor(f); k++) ctx.lineTo(line[k][0], line[k][1]);
  const [x, y] = pointAt(line, q);
  ctx.lineTo(x, y);
  ctx.stroke();
}

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

/** Where a core stands after `e` seconds, its width, height and opacity, or null before it shows. */
function corePlace(d: BrainDemo, core: BrainCore, e: number, zoom: number): [number, number, number, number, number] | null {
  const c = d.cells[core.source];
  if (e < c.born) return null;
  if (core.joins) {
    const q = d.reduced ? 1 : ease(clamp((e - c.born) / SLIDE, 0, 1));
    const a = clamp((e - c.born) / SLIDE, 0, 1);
    return [core.x, core.top + (1 - q) * core.h * 0.8, core.w, core.h, a];
  }
  const m = migration(d, e);
  if (m <= 0) return null;
  const p = c.story;
  const k = d.reduced ? (m < 0.5 ? 0 : 1) : m;
  if (d.reduced && k === 0) return null;
  const x = p ? p.x + (core.x - p.x) * k : core.x;
  const cy = p ? p.y + (core.top + core.h / 2 - p.y) * k : core.top + core.h / 2;
  const tile = Math.max(p ? p.r : TILE_PX, TILE_PX / zoom) * 2;
  const w = tile + (core.w - tile) * k,
    h = w * (core.h / core.w);
  return [x, cy - h / 2, w, h, d.reduced ? 1 : clamp(m * 2, 0, 1)];
}

/** Draws a core: a dark tower in its colour, four slots lit by `led`, a port on top. */
function drawCore(ctx: CanvasRenderingContext2D, color: string, x: number, top: number, w: number, h: number, alpha: number, led: number, e: number): void {
  const col = themedColour(color);
  const body = ctx.createLinearGradient(x - w / 2, top, x + w / 2, top + h);
  body.addColorStop(0, hex(mix(col, MIX_BLACK, 0.4), alpha));
  body.addColorStop(1, hex(mix(col, MIX_BLACK, 0.68), alpha));
  roundRect(ctx, x - w * 0.2, top - w * 0.07, w * 0.4, w * 0.14, w * 0.04);
  ctx.fillStyle = hex(mix(col, MIX_BLACK, 0.25), alpha);
  ctx.fill();
  roundRect(ctx, x - w / 2, top, w, h, w * 0.12);
  ctx.fillStyle = body;
  ctx.fill();
  ctx.strokeStyle = hex(mix(col, MIX_WHITE, 0.3), 0.8 * alpha);
  ctx.lineWidth = w * 0.03;
  ctx.stroke();
  for (let k = 0; k < 4; k++) {
    const shimmer = 0.75 + 0.25 * Math.sin(e * 4.2 + k * 1.9 + x * 0.01);
    roundRect(ctx, x - w * 0.32, top + h * (0.2 + k * 0.17), w * 0.64, h * 0.065, h * 0.03);
    ctx.fillStyle = hex(mix(col, MIX_WHITE, 0.6), alpha * (0.22 + 0.78 * led * shimmer));
    ctx.fill();
  }
}

/** How strongly the data run sends through a core after `e` seconds, 0 to 1. */
function sendOf(rig: BrainRig, j: number, e: number): number {
  let k = 0;
  for (const r of rig.runs) if (r.cores.includes(j)) k = Math.max(k, 1 - Math.abs(e - r.at - CABLE_RUN / 2) / CABLE_RUN);
  const all = e - rig.allAt;
  if (all >= 0) k = Math.max(k, all < CABLE_RUN * (ALL_STREAM + 1) ? 1 : 0);
  return clamp(k, 0, 1);
}

/** The cores, their cables and names: under the brain's cells. */
export function drawCores(ctx: CanvasRenderingContext2D, TH: CanvasTheme, d: BrainDemo, e: number, fade: number, zoom: number): void {
  const rig = d.rig;
  if (!rig) return;
  const cw0 = (w: number) => w * CABLE_SHARE;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  rig.cores.forEach((core, j) => {
    const place = corePlace(d, core, e, zoom);
    if (!place) return;
    const [x, top, w, h, a] = place;
    const alpha = a * fade;
    const color = d.cells[core.source].color;
    const col = themedColour(color);
    const plugged = e >= core.plugAt;
    const send = sendOf(rig, j, e);
    // The cable reaches up from the port and plugs in.
    if (e >= core.reachAt) {
      const q = d.reduced ? 1 : ease(clamp((e - core.reachAt) / PLUG, 0, 1));
      const k = d.reduced ? clamp((e - core.reachAt) / PLUG, 0, 1) : 1;
      const cw = cw0(core.w);
      for (const strand of core.strands) {
        ctx.strokeStyle = hex(mix(col, MIX_BLACK, 0.5), 0.95 * alpha * k);
        ctx.lineWidth = cw * 0.3;
        strokePart(ctx, strand, q);
        ctx.strokeStyle = hex(mix(col, MIX_WHITE, 0.4), (0.45 + 0.4 * send) * alpha * k);
        ctx.lineWidth = cw * 0.09;
        strokePart(ctx, strand, q);
      }
      if (plugged) {
        ctx.globalCompositeOperation = 'lighter';
        ctx.strokeStyle = hex(mix(col, MIX_WHITE, 0.7), (0.35 + 0.5 * send) * alpha);
        ctx.lineWidth = cw * 0.16;
        strokePart(ctx, core.cable, 1);
        ctx.globalCompositeOperation = 'source-over';
      }
      if (plugged) {
        const flash = d.reduced ? 0 : Math.max(0, 1 - (e - core.plugAt) / PLUG_FLASH);
        drawGlow(ctx, color, core.sx, core.sy, cw * 3.2, (PLUG_GLOW + 0.65 * Math.max(flash, send)) * fade);
        roundRect(ctx, core.sx - cw * 0.8, core.sy - cw * 0.1, cw * 1.6, cw * 0.9, cw * 0.25);
        ctx.fillStyle = hex(mix(col, MIX_BLACK, 0.3), alpha);
        ctx.fill();
        ctx.strokeStyle = hex(mix(col, MIX_WHITE, 0.55 + 0.45 * flash), alpha);
        ctx.lineWidth = cw * 0.12;
        ctx.stroke();
      }
    }
    const led = plugged ? 0.65 + 0.35 * send : 0.15;
    if (plugged) drawGlow(ctx, color, x, top + h / 2, w * 1.25, (0.3 + 0.5 * send) * fade);
    drawCore(ctx, color, x, top, w, h, alpha, led, d.reduced || d.instant ? 0 : e);
    // Its name, once it is more core than tile.
    if (w < core.w * 0.5) return;
    const size = Math.max(core.w * NAME_SHARE, NAME_PX / zoom);
    ctx.font = `600 ${Math.round(size * 100) / 100}px ${FONT_SANS}`;
    ctx.textAlign = 'center';
    ctx.shadowColor = TH.shadow;
    ctx.shadowBlur = 4;
    ctx.fillStyle = `rgba(${TH.INK},${0.88 * alpha})`;
    wrap(ctx, d.cells[core.source].label, core.pitch * 1.8).forEach((line, k) => ctx.fillText(line, x, top + h + size * (1.3 + k * 1.2)));
    ctx.shadowBlur = 0;
  });
}

/** How brightly the data run has lit a cell `a` seconds after the light reached it. */
const litOf = (a: number): number => (a < 0 ? 0 : a < LIT_RISE ? a / LIT_RISE : LIT_REST + (1 - LIT_REST) * Math.max(0, 1 - (a - LIT_RISE) / LIT_FALL));

/** How much of the lit cells' glow is left as the finale's wave takes over. */
const litLeft = (rig: BrainRig, e: number): number => 1 - clamp((e - rig.allAt - CABLE_RUN) / WAVE, 0, 1);

/** The halos of the cells the data run has lit: under the cells. */
export function drawRunGlow(ctx: CanvasRenderingContext2D, d: BrainDemo, e: number, fade: number, hidden: Set<string>, inRect: (x: number, y: number) => boolean): void {
  const rig = d.rig;
  if (!rig || !rig.runs.length || e < rig.runs[0].at) return;
  const left = litLeft(rig, e) * fade;
  if (left <= 0.01) return;
  const R = d.radius * LIT_R;
  for (const run of rig.runs) {
    if (e < run.at + CABLE_RUN || hidden.has(run.domain)) continue;
    for (const i of run.cells) {
      const g = litOf(e - rig.litAt[i]);
      if (g <= 0.01) continue;
      const c = d.cells[i];
      if (inRect(c.x, c.y)) drawGlow(ctx, c.color, c.x, c.y, R, g * left);
    }
  }
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

/** Everything over the brain's cells: the data run's sparks and flashes, the agents, their routes and the proposal. */
export function drawRigOver(
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

  // The data run: sparks up the cables and into the lobe, a flash on each cell the light reaches.
  if (!still && rig.runs.length && e >= rig.runs[0].at && e < rig.allAt + CABLE_RUN * (ALL_STREAM + 2)) {
    for (const run of rig.runs) {
      const t = e - run.at;
      if (t < 0 || t > CABLE_RUN + 2 || hidden.has(run.domain)) continue;
      const head = d.cells[run.cells[0]].color;
      for (const j of run.cores) {
        const core = rig.cores[j];
        const cw = core.w * CABLE_SHARE;
        for (let k = 0; k < 3; k++) {
          const q = t / CABLE_RUN - k * 0.18;
          if (q <= 0 || q >= 1) continue;
          const [x0, y0] = pointAt(core.cable, q - 0.12),
            [x1, y1] = pointAt(core.cable, q);
          pulses.segment(d.cells[core.source].color, head, x0, y0, x1, y1, fade, cw * 0.6, cw * 0.25);
        }
      }
      const [ex, ey] = run.entry;
      for (const i of run.sparks) {
        const c = d.cells[i];
        const leave = run.at + CABLE_RUN,
          arrive = rig.litAt[i];
        const q = (e - leave) / Math.max(0.05, arrive - leave);
        if (q > 0 && q < 1) pulses.add(head, c.color, ex, ey, c.x, c.y, ease(q), fade);
      }
      ctx.globalCompositeOperation = 'lighter';
      for (const i of run.cells) {
        const a = e - rig.litAt[i];
        if (a < 0 || a > LIT_FLASH) continue;
        const c = d.cells[i];
        ctx.globalAlpha = 0.7 * (1 - a / LIT_FLASH) * fade;
        drawSphere(ctx, c.color, c.x, c.y, d.radius);
      }
      ctx.globalCompositeOperation = 'source-over';
      ctx.globalAlpha = 1;
    }
    const t = e - rig.allAt;
    if (t >= 0)
      for (const core of rig.cores) {
        const cw = core.w * CABLE_SHARE;
        for (let k = 0; k < ALL_SPARKS; k++) {
          const q = t / CABLE_RUN - (k * ALL_STREAM) / ALL_SPARKS;
          if (q <= 0 || q >= 1) continue;
          const [x0, y0] = pointAt(core.cable, q - 0.12),
            [x1, y1] = pointAt(core.cable, q);
          pulses.segment(d.cells[core.source].color, d.cells[core.source].color, x0, y0, x1, y1, fade, cw * 0.7, cw * 0.25);
        }
      }
  }

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
