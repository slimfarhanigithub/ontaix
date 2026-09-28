/**
 * Physics: division tweens, differentiation, repulsion, springs, gravity toward the domain
 * centre, dying removal and the camera. Ported from reference/ontaix-studio-reference.html
 * lines 311-333 (`step`).
 */
import { now } from '../runtime/clock';
import { random } from '../runtime/rng';
import { clamp, ease, mix } from './colour';
import { MOTION } from './constants';
import { domainCentre, shown, type SceneState } from './state';
import { panelW, type View } from './view';

export function step(s: SceneState, v: View, dt: number): void {
  const t = now();
  const { nodes, links, cam } = s;
  for (const n of nodes) {
    if (n.split) {
      const m = n.split,
        p = clamp((t - m.start) / m.dur, 0, 1);
      const q = clamp((p - 0.2) / 0.8, 0, 1);
      const D = m.D * ease(q);
      n.x = m.from.x + Math.cos(m.ang) * D;
      n.y = m.from.y + Math.sin(m.ang) * D;
      n.vx = n.vy = 0;
      if (!m.kicked && q > 0) {
        m.kicked = true;
        if (!m.from.fixed && !m.from.pinned) {
          m.from.vx -= Math.cos(m.ang) * 55;
          m.from.vy -= Math.sin(m.ang) * 55;
        }
      }
      if (!m.broken && D > (n.r + m.from.r) * 1.28) {
        m.broken = true;
        if (!s.SKIP) {
          n.recoil = { start: t, ang: m.ang };
          m.from.recoil = { start: t, ang: m.ang };
        }
      }
      if (p >= 1) {
        n.split = null;
        n.diff = { start: t };
        n.vx = Math.cos(m.ang) * (m.D > n.rt * 3.2 ? 0 : 70);
        n.vy = Math.sin(m.ang) * (m.D > n.rt * 3.2 ? 0 : 70);
        for (const l of links)
          if (l.a === n || l.b === n) {
            l.grow = { start: t };
            l.alpha = 0;
            l.pulses.length = 0;
          }
      }
    } else if (n.diff) {
      const q = s.SKIP ? 1 : clamp((t - n.diff.start) / 0.25, 0, 1);
      n.color = mix(n.cloneColor as string, n.finalColor as string, ease(q));
      n.labelAlpha = q;
      if (q >= 1) {
        n.diff = null;
        n.color = n.finalColor as string;
        n.labelAlpha = 1;
      }
    }
  }
  for (let i = 0; i < nodes.length; i++) {
    const a = nodes[i];
    for (let j = i + 1; j < nodes.length; j++) {
      const b = nodes[j];
      if ((a.split && a.split.from === b) || (b.split && b.split.from === a)) continue;
      let dx = b.x - a.x,
        dy = b.y - a.y,
        d2 = dx * dx + dy * dy;
      if (d2 < 1) {
        dx = random() - 0.5;
        dy = random() - 0.5;
        d2 = 1;
      }
      const d = Math.sqrt(d2);
      const want = (a.rt + b.rt) * 3.6;
      if (d < want) {
        const f = ((want - d) / want) * 950,
          fx = (dx / d) * f,
          fy = (dy / d) * f;
        if (!a.fixed && !a.drag) {
          a.vx -= fx * dt;
          a.vy -= fy * dt;
        }
        if (!b.fixed && !b.drag) {
          b.vx += fx * dt;
          b.vy += fy * dt;
        }
      }
    }
  }
  for (const l of links) {
    const a = l.a,
      b = l.b;
    if (a.split || b.split) continue;
    const dx = b.x - a.x,
      dy = b.y - a.y,
      d = Math.hypot(dx, dy) || 1;
    const f = (d - l.rest) * 6,
      fx = (dx / d) * f,
      fy = (dy / d) * f;
    if (!a.fixed && !a.drag) {
      a.vx += fx * dt;
      a.vy += fy * dt;
    }
    if (!b.fixed && !b.drag) {
      b.vx -= fx * dt;
      b.vy -= fy * dt;
    }
  }
  for (const n of nodes) {
    if (n.tween) {
      const q = clamp((t - n.tween.start) / 1.3, 0, 1);
      n.x = n.tween.fx + (n.tween.tx - n.tween.fx) * ease(q);
      n.y = n.tween.fy + (n.tween.ty - n.tween.fy) * ease(q);
      n.vx = n.vy = 0;
      if (q >= 1) {
        const pin = n.tween.pin !== false;
        n.tween = null;
        n.pinned = pin;
      }
      continue;
    }
    if (n.kind === 'source') {
      if (!n.drag && n.anchor) {
        n.x += (n.anchor[0] - n.x) * 0.08;
        n.y += (n.anchor[1] - n.y) * 0.08;
      }
      n.r = n.rt;
      continue;
    }
    if (n.drag || n.split || n.pinned) {
      n.vx = n.vy = 0;
      continue;
    }
    if (n.fixed) {
      n.x = n.company ? n.company.x : 0;
      n.y = n.company ? n.company.y : 0;
      n.vx = n.vy = 0;
      continue;
    }
    const [gx, gy] = n.domain ? domainCentre(n.domain) : [n.company ? n.company.x : 0, n.company ? n.company.y : 0];
    n.vx -= (n.x - gx) * 1.3 * dt;
    n.vy -= (n.y - gy) * 1.3 * dt;
    if (n.conflict) {
      n.vx += (random() - 0.5) * 300 * dt;
      n.vy += (random() - 0.5) * 300 * dt;
    }
    n.vx *= 0.86;
    n.vy *= 0.86;
    n.x += n.vx * dt;
    n.y += n.vy * dt;
  }
  for (const n of nodes) n.alpha = Math.min(1, n.alpha + dt * 1.6);
  for (let i = nodes.length; i--; ) {
    const n = nodes[i];
    if (n.dying && t - n.dying.start > 0.7) {
      nodes.splice(i, 1);
      for (let j = links.length; j--; ) if (links[j].a === n || links[j].b === n) links.splice(j, 1);
    }
  }
  for (const l of links) {
    l.alpha = Math.min(1, l.alpha + dt * 1.4);
  }
  if (!s.userZoomed && nodes.length > 1 && !s.dragging && !s.panning) {
    let x0 = 1e9,
      y0 = 1e9,
      x1 = -1e9,
      y1 = -1e9;
    for (const n of nodes) {
      if (n.dying || !shown(n)) continue;
      x0 = Math.min(x0, n.x);
      y0 = Math.min(y0, n.y);
      x1 = Math.max(x1, n.x);
      y1 = Math.max(y1, n.y);
    }
    const bw = x1 - x0 + 2 * (175 + 80),
      bh = y1 - y0 + 2 * (175 + 70);
    cam.ts = clamp(Math.min((v.W - panelW(v) - 60) / bw, (v.H - 250) / bh), 0.32, 1);
    cam.tx = (x0 + x1) / 2;
    cam.ty = (y0 + y1) / 2 + 20;
  } else if (t - s.lastInteract > 6 && cam.ts === 1 && !s.running && !nodes.some((n) => n.pinned)) {
    cam.tx = Math.sin(t * 0.11) * 30 * MOTION;
    cam.ty = Math.cos(t * 0.09) * 22 * MOTION;
  }
  cam.s += (cam.ts - cam.s) * Math.min(1, dt * 2.4);
  cam.x += (cam.tx - cam.x) * Math.min(1, dt * 2.4);
  cam.y += (cam.ty - cam.y) * Math.min(1, dt * 2.4);
}
