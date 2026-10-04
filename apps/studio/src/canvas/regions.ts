/**
 * Background, company hulls and domain regions. Ported from
 * reference/ontaix-studio-reference.html lines 342-344 (`background`), 350-376
 * (`drawCompanies`, `drawDomains`).
 */
import { hex, mix } from './colour';
import { FONT_SANS, themedColour, token } from '../design/tokens';
import { OFFS } from './constants';
import { hull, type Pt } from './hulls';
import { shown, type SceneState } from './state';
import type { Company, Domain, Node } from './types';
import { CX, type View } from './view';

export function background(v: View): void {
  const { ctx, TH, W, H } = v;
  ctx.setTransform(v.DPR, 0, 0, v.DPR, 0, 0);
  ctx.fillStyle = TH.bg;
  ctx.fillRect(0, 0, W, H);
  const g = ctx.createRadialGradient(CX(v), H * 0.45, 0, CX(v), H * 0.45, Math.max(W, H) * 0.7);
  g.addColorStop(0, hex(token('--accent'), 0.04));
  g.addColorStop(0.6, hex(token('--link'), 0.025));
  g.addColorStop(1, `rgba(${TH.CHIP},0)`);
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);
  const vg = ctx.createRadialGradient(CX(v), H / 2, Math.min(W, H) * 0.35, CX(v), H / 2, Math.max(W, H) * 0.75);
  vg.addColorStop(0, `rgba(${TH.CHIP},0)`);
  vg.addColorStop(1, TH.vignette);
  ctx.fillStyle = vg;
  ctx.fillRect(0, 0, W, H);
}

/** Prepares the half-resolution layer in the current world transform; false when too small. */
function beginLayer(v: View): boolean {
  const { canvas, off, octx, ctx } = v;
  const w = Math.max(1, Math.round(canvas.width * OFFS)),
    h = Math.max(1, Math.round(canvas.height * OFFS));
  if (off.width !== w || off.height !== h) {
    off.width = w;
    off.height = h;
  }
  if (w < 2 || h < 2) return false;
  octx.setTransform(1, 0, 0, 1, 0, 0);
  octx.clearRect(0, 0, w, h);
  const m = ctx.getTransform();
  octx.setTransform(m.a * OFFS, m.b * OFFS, m.c * OFFS, m.d * OFFS, m.e * OFFS, m.f * OFFS);
  return true;
}

function fillHull(octx: CanvasRenderingContext2D, pts: Pt[], pad: number, col: string): void {
  octx.beginPath();
  if (pts.length === 1) {
    octx.arc(pts[0][0], pts[0][1], 1, 0, 6.283);
  } else {
    octx.moveTo(pts[0][0], pts[0][1]);
    for (let i = 1; i < pts.length; i++) octx.lineTo(pts[i][0], pts[i][1]);
    octx.closePath();
  }
  octx.lineJoin = 'round';
  octx.lineCap = 'round';
  octx.lineWidth = pad * 2;
  octx.strokeStyle = col;
  octx.stroke();
  octx.fillStyle = col;
  octx.fill();
}

function compositeLayer(v: View, alpha: number, smooth: boolean): void {
  const { ctx, off, canvas } = v;
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.globalAlpha = alpha;
  if (smooth) ctx.imageSmoothingEnabled = true;
  ctx.drawImage(off, 0, 0, canvas.width, canvas.height);
  ctx.restore();
}

export function drawCompanies(s: SceneState, v: View, _t: number): void {
  if (!beginLayer(v)) return;
  const { ctx, octx, TH } = v;
  const pad = 175;
  const heads: [Company, Node[], number, number][] = [];
  let any = false;
  for (const c of s.companies) {
    const members = s.nodes.filter((n) => n.company === c && !n.dying && shown(n) && n.kind !== 'source');
    if (!members.length) continue;
    any = true;
    const pts = hull(members.map((n) => [n.x, n.y] as Pt));
    fillHull(octx, pts, pad, TH.hull);
    if (s.cam.s > 0.28)
      heads.push([c, members, Math.min(...members.map((n) => n.y)), members.reduce((a, n) => a + n.x, 0) / members.length]);
  }
  if (any) compositeLayer(v, TH.hullA, false);
  for (const [c, members, minY, cx] of heads) {
    const concepts = members.filter((n) => n.kind === 'concept').length,
      bound = members.filter((n) => n.bound).length,
      doms = c.domains.filter((d) => members.some((n) => n.domain === d)).length,
      src = s.nodes.filter((n) => n.kind === 'source' && n.company === c && !n.pending && !n.dying).length;
    // The title and its subtitle grow together when the camera zooms out, and the gap between them with them.
    const k = 1 / Math.max(s.cam.s, 0.5);
    ctx.textAlign = 'center';
    ctx.fillStyle = `rgba(${TH.INK},0.95)`;
    ctx.font = `600 ${Math.round(15 * k)}px ${FONT_SANS}`;
    ctx.fillText(c.name.toUpperCase(), cx, minY - pad - 8 - Math.round(18 * k));
    ctx.fillStyle = `rgba(${TH.INK2},0.85)`;
    ctx.font = `300 ${Math.round(11 * k)}px ${FONT_SANS}`;
    ctx.fillText(
      `${c.sub ? c.sub + ' · ' : ''}business as a product · ${doms} domain product${doms === 1 ? '' : 's'} · ${concepts} concept${concepts === 1 ? '' : 's'}${src ? ` · ${src} source${src === 1 ? '' : 's'}` : ''}${s.COVERAGE ? ` · ${concepts ? Math.round((bound / concepts) * 100) : 0} % bound` : ''}`,
      cx,
      minY - pad - 8,
    );
  }
}

export function drawDomains(s: SceneState, v: View, _t: number): void {
  if (!beginLayer(v)) return;
  const { ctx, octx, TH } = v;
  const pad = 86;
  const headers: [Domain, Node[], number, number][] = [];
  let any = false;
  for (const d of s.DOMAINS) {
    if (d.hidden) continue;
    const members = s.nodes.filter((n) => n.domain === d && !n.dying);
    if (!members.length) continue;
    any = true;
    const pts = hull(members.map((n) => [n.x, n.y] as Pt));
    const dc = themedColour(d.color);
    const col = s.domainFocus === d ? dc : s.domainFocus ? mix(dc, TH.bg, 0.55) : dc;
    fillHull(octx, pts, pad, col);
    if (s.cam.s > 0.4)
      headers.push([d, members, Math.min(...members.map((n) => n.y)), members.reduce((a, n) => a + n.x, 0) / members.length]);
  }
  if (any) compositeLayer(v, s.domainFocus ? TH.domFocusA : TH.domA, true);
  for (const [d, members, minY, cx] of headers) {
    const pending = members.filter((n) => n.pending).length;
    const bnd = members.filter((n) => n.bound).length;
    ctx.textAlign = 'center';
    ctx.fillStyle = hex(themedColour(d.color), 0.95);
    ctx.font = `500 12.5px ${FONT_SANS}`;
    ctx.fillText((s.companies.length > 1 ? d.company.name + ' · ' : '') + d.name.toUpperCase(), cx, minY - pad - 18);
    ctx.fillStyle = `rgba(${TH.INK2},0.85)`;
    ctx.font = `300 10.5px ${FONT_SANS}`;
    ctx.fillText(
      `domain product · ${d.owner} · v${d.version.toFixed(1)} · ${members.length - pending} concept${members.length - pending === 1 ? '' : 's'}${pending ? ` · ${pending} pending` : ''}${s.COVERAGE ? ` · ${bnd} of ${members.length} bound` : ''}`,
      cx,
      minY - pad - 3,
    );
  }
}
