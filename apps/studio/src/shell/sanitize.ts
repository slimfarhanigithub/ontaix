/**
 * Allow-list sanitiser for the proposal text the API sends as HTML. Only `b`, `i`, `em` and
 * `span` (with its `class`) survive as elements; every other tag is shown as literal text and
 * every attribute other than `span.class` is dropped. The client never trusts the server here.
 */

const ALLOWED = new Set(['B', 'I', 'EM', 'SPAN']);

export const escapeHtml = (s: string): string =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

function serialise(node: Node): string {
  if (node.nodeType === Node.TEXT_NODE) return escapeHtml(node.textContent || '');
  if (node.nodeType !== Node.ELEMENT_NODE) return '';
  const el = node as Element;
  const inner = Array.from(el.childNodes).map(serialise).join('');
  if (!ALLOWED.has(el.tagName)) return escapeHtml(`<${el.tagName.toLowerCase()}>`) + inner + escapeHtml(`</${el.tagName.toLowerCase()}>`);
  const tag = el.tagName.toLowerCase();
  const cls = tag === 'span' && el.getAttribute('class') ? ` class="${escapeHtml(el.getAttribute('class') || '')}"` : '';
  return `<${tag}${cls}>${inner}</${tag}>`;
}

/** Returns markup safe to inject: allowed tags kept without attributes, everything else escaped. */
export function sanitizeHtml(html: string): string {
  const doc = new DOMParser().parseFromString(`<body>${html}</body>`, 'text/html');
  return Array.from(doc.body.childNodes).map(serialise).join('');
}
