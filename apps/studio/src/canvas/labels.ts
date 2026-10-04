/**
 * Text and chip helpers shared by the cell and link renderers. Ported from
 * reference/ontaix-studio-reference.html line 340 (`roundRect`) and the label blocks of
 * `drawCell` (lines 462-466) and `drawSource` (line 450).
 */
import { FONT_SANS, themedColour } from '../design/tokens';
import { hex } from './colour';
import type { SceneState } from './state';
import type { Node } from './types';
import type { View } from './view';

export function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number): void {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

/** Label, sub line and data line under a cell. */
export function drawCellLabels(s: SceneState, v: View, n: Node, al: number, col: string, r: number, hot: boolean): void {
  const { ctx, TH } = v;
  if (!(s.cam.s > 0.45 && n.labelAlpha > 0)) return;
  const la = al * n.labelAlpha;
  ctx.textAlign = 'center';
  ctx.fillStyle = `rgba(${TH.INK},${0.95 * la})`;
  ctx.font = `${hot ? '600' : '500'} ${n.kind === 'root' ? 15 : 13}px ${FONT_SANS}`;
  ctx.shadowColor = TH.shadow;
  ctx.shadowBlur = 4;
  ctx.fillText(n.label, n.x, n.y + r + 24);
  ctx.shadowBlur = 0;
  let yy = n.y + r + 39;
  if (n.sub) {
    ctx.fillStyle = hex(themedColour(col), 0.95 * la);
    ctx.font = `300 11px ${FONT_SANS}`;
    ctx.fillText(n.sub, n.x, yy);
    yy += 14;
  } else if (n.pending && !n.split) {
    ctx.fillStyle = `rgba(${TH.INK2},${0.8 * la})`;
    ctx.font = `300 10.5px ${FONT_SANS}`;
    ctx.fillText('awaiting approval', n.x, yy);
    yy += 14;
  }
  if (n.bound) {
    ctx.fillStyle = `rgba(${TH.INK2},${0.95 * la})`;
    ctx.font = `400 10.5px ${FONT_SANS}`;
    ctx.fillText(
      `${n.bound.records.toLocaleString('en-GB')} records · ${n.bound.source.label} · fresh ${n.bound.fresh}`,
      n.x,
      yy,
    );
  } else if (s.COVERAGE && n.kind === 'concept') {
    ctx.fillStyle = `rgba(${TH.INK2},${0.7 * la})`;
    ctx.font = `300 10.5px ${FONT_SANS}`;
    ctx.fillText('no data behind it', n.x, yy);
  }
}

/** Label and status line under a source square. */
export function drawSourceLabels(s: SceneState, v: View, n: Node, al: number, r: number, hot: boolean): void {
  const { ctx, TH } = v;
  if (!(s.cam.s > 0.4)) return;
  ctx.textAlign = 'center';
  ctx.fillStyle = `rgba(${TH.INK},${0.95 * al})`;
  ctx.font = `${hot ? '600' : '500'} 13px ${FONT_SANS}`;
  ctx.shadowColor = TH.shadow;
  ctx.shadowBlur = 4;
  ctx.fillText(n.label, n.x, n.y + r + 22);
  ctx.shadowBlur = 0;
  ctx.fillStyle = `rgba(${TH.INK2},${0.8 * al})`;
  ctx.font = `300 10.5px ${FONT_SANS}`;
  const bound = s.links.filter((l) => l.kind === 'bind' && l.a === n && !l.pending).length;
  ctx.fillText(
    `${n.sub}${bound ? ` · ${bound} concept${bound === 1 ? '' : 's'}` : ''}${n.pending ? ' · awaiting approval' : ''}`,
    n.x,
    n.y + r + 37,
  );
}
