/**
 * The room a cell and an action chip take on the canvas, read from what the renderer draws: the
 * label lines under a cell or a source (`labels.ts`) and the chip at the middle of a link
 * (`links.ts`). Arrange reserves this room so that nothing it places covers anything else.
 */
import type { Link, Node } from './types';

/** Width in pixels of `text` drawn in the CSS `font`. */
export type Measure = (text: string, font: string) => number;

/** Extents of a cell and its labels around the cell centre. */
export interface Footprint {
  /** Half the width of the widest of the cell and its label lines. */
  halfW: number;
  /** Extent above the centre. */
  up: number;
  /** Extent below the centre, down to the last label line. */
  down: number;
}

/** Height of the action chip drawn on a link. */
export const CHIP_H = 18;
/** Padding the renderer adds around the action text inside its chip. */
const CHIP_PAD = 16;
/** Distance between two label lines under a cell. */
const LINE = 14;
/** Room for the bolder hover weight of a label and the text shadow. */
const SLACK = 1.06;

/** Width of the action chip of a link; 0 for a link without an action. */
export function chipWidth(l: Pick<Link, 'kind' | 'label'>, measure: Measure): number {
  if (!l.label) return 0;
  return measure(l.label, `${l.kind === 'isa' ? '300' : '500'} 10.5px Sora, sans-serif`) + CHIP_PAD;
}

/**
 * The cell and every label line the renderer may draw under it. A concept always reserves the
 * third line, which the Coverage view fills with `no data behind it` when nothing is bound.
 */
export function cellFootprint(n: Node, measure: Measure): Footprint {
  const r = Math.max(n.r, n.rt);
  if (n.kind === 'source') {
    const widths = [
      measure(n.label, '600 13px Sora, sans-serif'),
      measure(`${n.sub} · 99 concepts${n.pending ? ' · awaiting approval' : ''}`, '300 10.5px Sora, sans-serif'),
    ];
    return { halfW: Math.max(r + 4, (Math.max(...widths) * SLACK) / 2 + 4), up: r + 4, down: r + 37 + 5 };
  }
  const widths = [measure(n.label, `600 ${n.kind === 'root' ? 15 : 13}px Sora, sans-serif`)];
  let lines = 1;
  if (n.sub) {
    widths.push(measure(n.sub, '300 11px Sora, sans-serif'));
    lines++;
  } else if (n.pending) {
    widths.push(measure('awaiting approval', '300 10.5px Sora, sans-serif'));
    lines++;
  }
  if (n.bound) {
    widths.push(
      measure(
        `${n.bound.records.toLocaleString('en-GB')} records · ${n.bound.source.label} · fresh ${n.bound.fresh}`,
        '400 10.5px Sora, sans-serif',
      ),
    );
    lines++;
  } else if (n.kind === 'concept') {
    widths.push(measure('no data behind it', '300 10.5px Sora, sans-serif'));
    lines++;
  }
  return {
    halfW: Math.max(r + 4, (Math.max(...widths) * SLACK) / 2 + 4),
    up: r + 4,
    down: r + 24 + 5 + LINE * (lines - 1),
  };
}

/** Average advance of Sora glyphs as a share of the font size, by glyph class. */
const NARROW = new Set([...'iljtfr.,:;\'!| ()[]-']);
const WIDE = new Set([...'mwMW@%&']);

/**
 * A close estimate of Sora text widths, for places with no 2D context (tests, workers). It runs
 * a little wide, so room reserved from it is never short.
 */
export const estimateWidth: Measure = (text, font) => {
  const m = /(\d+(?:\.\d+)?)px/.exec(font);
  const px = m ? Number(m[1]) : 13;
  let em = 0;
  for (const ch of text) {
    if (NARROW.has(ch)) em += 0.34;
    else if (WIDE.has(ch)) em += 0.92;
    else if (ch >= 'A' && ch <= 'Z') em += 0.72;
    else em += 0.62;
  }
  return em * px;
};

/** Measures with a 2D context, one measurement per text and font. */
export function measureWith(ctx: CanvasRenderingContext2D): Measure {
  const cache = new Map<string, number>();
  return (text, font) => {
    const key = `${font}\u0000${text}`;
    let w = cache.get(key);
    if (w === undefined) {
      const was = ctx.font;
      ctx.font = font;
      w = ctx.measureText(text).width;
      ctx.font = was;
      cache.set(key, w);
    }
    return w;
  };
}
