/**
 * Document extraction of the in-browser mock, mirroring `POST /import/sentences`: file name and
 * media type checks, sniffing of the bytes against the declared type, the size, text and sentence
 * limits, and sentence splitting. Plain text, Markdown, CSV and JSON are decoded as UTF-8; Word,
 * PowerPoint and Excel documents are read from their ZIP archive with no DTD, and refused when
 * macro-enabled or a legacy binary file; HTML is parsed without running or fetching anything;
 * PDF text is read from its literal text operators, a best effort for simple files; the mock has
 * no OCR, so a scanned PDF yields no sentences.
 * Sentences are split the way reference/ontaix-studio-reference.html line 900 (`sentencesOf`)
 * does, per paragraph when the paragraph is known.
 */
import type { DocumentPosition, ImportMediaType } from '../types';

export const IMPORT_MAX_BYTES = 10 * 1024 * 1024;
const MAX_CHARS = 2_000_000;
const MAX_SENTENCES = 2000;
const MAX_ARCHIVE_MEMBERS = 1000;
const MAX_FILE_NAME_BYTES = 1020;
const MAX_FILE_NAME_CHARS = 255;
const DOCX: ImportMediaType = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
const PPTX: ImportMediaType = 'application/vnd.openxmlformats-officedocument.presentationml.presentation';
const XLSX: ImportMediaType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
const HTML: ImportMediaType = 'text/html';
const WORD_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main';
const DRAWING_NS = 'http://schemas.openxmlformats.org/drawingml/2006/main';
const SHEET_NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';
const MAIN_TYPES: Record<string, ImportMediaType> = {
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml': DOCX,
  'application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml': PPTX,
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml': XLSX,
};
const TEXT_TYPES = new Set<string>(['text/plain', 'text/markdown', 'text/csv', 'application/json']);
const DROPPED_HTML = 'script,style,template,noscript,iframe,object,embed,svg,math';
const BLOCK_HTML = new Set(
  'address article aside blockquote body caption dd details div dl dt figcaption figure footer form h1 h2 h3 h4 h5 h6 header li main nav ol p pre section summary table td th title tr ul'.split(
    ' ',
  ),
);

const BY_EXTENSION: Record<string, ImportMediaType> = {
  txt: 'text/plain',
  md: 'text/markdown',
  markdown: 'text/markdown',
  csv: 'text/csv',
  json: 'application/json',
  docx: DOCX,
  pdf: 'application/pdf',
  pptx: PPTX,
  xlsx: XLSX,
  html: HTML,
  htm: HTML,
};
const MEDIA_TYPES = new Set<string>(Object.values(BY_EXTENSION));
const REFUSED_NAME_CHARS =
  /[/\\:\u0000-\u001f\u007f-\u009f\u061c\u200b-\u200f\u2028\u2029\u202a-\u202e\u2066-\u2069\ufeff]/;

export class ExtractRefusal extends Error {
  constructor(
    public status: number,
    public code: string,
    public detail: string,
  ) {
    super(detail);
  }
}

export interface ExtractedSentence {
  text: string;
  position: DocumentPosition | null;
}

export interface Extracted {
  fileName: string;
  mediaType: ImportMediaType;
  sentences: ExtractedSentence[];
}

/** Splits text into sentences of 13 to 399 characters. */
export function sentencesOf(text: string): string[] {
  return text
    .replace(/\s+/g, ' ')
    .split(/(?<=[.!?])\s+|\n+/)
    .map((x) => x.trim())
    .filter((x) => x.length > 12 && x.length < 400);
}

/** The basename of an uploaded file name, refused (never rewritten) when it breaks a rule. */
export function checkedFileName(raw: string): string {
  const name = raw.split(/[/\\]/).pop() || '';
  const bytes = new TextEncoder().encode(name).length;
  if (!name || name.length > MAX_FILE_NAME_CHARS || bytes > MAX_FILE_NAME_BYTES || REFUSED_NAME_CHARS.test(name))
    throw new ExtractRefusal(422, 'validation_failed', 'the file name is empty, too long or holds a refused character');
  return name;
}

export function mediaTypeOf(fileName: string, contentType: string): ImportMediaType {
  const ext = fileName.includes('.') ? fileName.split('.').pop()!.toLowerCase() : '';
  const byExt = BY_EXTENSION[ext];
  if (byExt) return byExt;
  const declared = contentType.split(';')[0].trim().toLowerCase();
  if (MEDIA_TYPES.has(declared)) return declared as ImportMediaType;
  throw new ExtractRefusal(
    415,
    'unsupported_media_type',
    'text, Markdown, CSV, JSON, HTML, Word, PowerPoint, Excel and PDF documents are supported',
  );
}

export async function extractDocument(rawName: string, contentType: string, bytes: Uint8Array): Promise<Extracted> {
  const fileName = checkedFileName(rawName);
  const mediaType = mediaTypeOf(fileName, contentType);
  if (bytes.length > IMPORT_MAX_BYTES) throw tooLarge('the document is larger than 10 MiB');
  const mismatch = await contentMismatch(bytes, mediaType);
  if (mismatch) throw new ExtractRefusal(415, 'unsupported_media_type', mismatch);
  const units = await unitsOf(mediaType, bytes);
  let chars = 0;
  const sentences: ExtractedSentence[] = [];
  for (const unit of units) {
    chars += unit.text.length;
    if (chars > MAX_CHARS) throw tooLarge('the document holds more than 2,000,000 characters of text');
    for (const text of sentencesOf(unit.text)) sentences.push({ text, position: unit.position });
    if (sentences.length > MAX_SENTENCES) throw tooLarge('the document holds more than 2,000 sentences');
  }
  return { fileName, mediaType, sentences };
}

/** Why the bytes are not a file of the media type: the type is sniffed from the bytes - a PDF
 * signature, an Office archive with exactly one main part and no macros, HTML text, or other
 * UTF-8 text - and must agree with the declared one. Legacy binary Office files are refused. */
export async function contentMismatch(bytes: Uint8Array, mediaType: ImportMediaType): Promise<string | null> {
  const sniffed = await sniff(bytes);
  if (sniffed === 'refused') return 'legacy, macro-enabled or unknown Office files are not read';
  if (sniffed === 'text') return TEXT_TYPES.has(mediaType) ? null : 'the file is text, not the type its name says';
  return sniffed === mediaType ? null : 'the file is not the type its name says';
}

async function sniff(bytes: Uint8Array): Promise<ImportMediaType | 'text' | 'refused'> {
  const ole = [0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1];
  if (ole.every((b, i) => bytes[i] === b)) return 'refused';
  if (new TextDecoder('latin1').decode(bytes.subarray(0, 1024)).includes('%PDF-')) return 'application/pdf';
  if (bytes[0] === 0x50 && bytes[1] === 0x4b && bytes[2] === 0x03 && bytes[3] === 0x04) {
    try {
      const names = zipNames(bytes);
      if (names.some((n) => n.toLowerCase().split('/').pop() === 'vbaproject.bin')) return 'refused';
      const types = Array.from(
        xml(await zipMember(bytes, '[Content_Types].xml')).getElementsByTagName('Override'),
      ).map((o) => (o.getAttribute('ContentType') || '').toLowerCase());
      if (types.some((t) => t.includes('macroenabled'))) return 'refused';
      const mains = types.filter((t) => t.endsWith('.main+xml'));
      return mains.length === 1 && MAIN_TYPES[mains[0]] ? MAIN_TYPES[mains[0]] : 'refused';
    } catch {
      return 'refused';
    }
  }
  let text: string;
  try {
    text = bytes[0] === 0xff && bytes[1] === 0xfe ? new TextDecoder('utf-16le').decode(bytes) : new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  } catch {
    return 'refused';
  }
  return /^\s*<(!doctype html|html|head|body)/i.test(text.replace(/^\ufeff/, '')) ? HTML : 'text';
}

const tooLarge = (detail: string) => new ExtractRefusal(413, 'payload_too_large', detail);
const unreadable = (detail: string) => new ExtractRefusal(422, 'validation_failed', detail);

async function unitsOf(mediaType: ImportMediaType, bytes: Uint8Array): Promise<ExtractedSentence[]> {
  if (mediaType === DOCX) return docxParagraphs(bytes);
  if (mediaType === PPTX) return pptxSlides(bytes);
  if (mediaType === XLSX) return xlsxRows(bytes);
  if (mediaType === HTML) return htmlParagraphs(bytes);
  if (mediaType === 'application/pdf') return [{ text: await pdfText(bytes), position: null }];
  const text = new TextDecoder('utf-8').decode(bytes);
  if (mediaType === 'text/csv')
    return [
      {
        text: text
          .split(/\r?\n/)
          .map((r) =>
            r
              .split(/[;,\t]/)
              .map((c) => c.trim())
              .filter(Boolean)
              .join(' '),
          )
          .join('. '),
        position: null,
      },
    ];
  return [{ text, position: null }];
}

/** Paragraph texts of `word/document.xml`, 1-based. */
async function docxParagraphs(bytes: Uint8Array): Promise<ExtractedSentence[]> {
  const xml = new TextDecoder('utf-8').decode(await zipMember(bytes, 'word/document.xml'));
  if (/<!DOCTYPE/i.test(xml)) throw unreadable('the Word document declares a DTD');
  const doc = new DOMParser().parseFromString(xml, 'application/xml');
  if (doc.getElementsByTagName('parsererror').length) throw unreadable('the Word document is not well-formed');
  const paragraphs = Array.from(doc.getElementsByTagNameNS(WORD_NS, 'p'));
  return paragraphs.map((p, i) => ({
    text: Array.from(p.getElementsByTagNameNS(WORD_NS, 't'))
      .map((t) => t.textContent || '')
      .join(''),
    position: { unit: 'paragraph', index: i + 1 },
  }));
}

/** An XML part parsed with no DTD. */
function xml(part: Uint8Array): Document {
  const text = new TextDecoder('utf-8').decode(part);
  if (/<!DOCTYPE/i.test(text)) throw unreadable('the document declares a DTD');
  const doc = new DOMParser().parseFromString(text, 'application/xml');
  if (doc.getElementsByTagName('parsererror').length) throw unreadable('the document is not well-formed');
  return doc;
}

/** Relationship ids to part names, for one part's `_rels` file. */
async function relationships(bytes: Uint8Array, part: string): Promise<Map<string, string>> {
  const dir = part.includes('/') ? part.slice(0, part.lastIndexOf('/') + 1) : '';
  const rels = `${dir}_rels/${part.slice(dir.length)}.rels`;
  const out = new Map<string, string>();
  if (!zipNames(bytes).includes(rels)) return out;
  for (const r of Array.from(xml(await zipMember(bytes, rels)).getElementsByTagName('Relationship'))) {
    if (r.getAttribute('TargetMode') === 'External') continue;
    const target = r.getAttribute('Target') || '';
    const parts = (target.startsWith('/') ? target.slice(1) : dir + target).split('/');
    const resolved: string[] = [];
    for (const p of parts) p === '..' ? resolved.pop() : p !== '.' && resolved.push(p);
    out.set(r.getAttribute('Id') || '', resolved.join('/'));
  }
  return out;
}

/** Slide text and speaker notes in slide order, at most 500 slides. */
async function pptxSlides(bytes: Uint8Array): Promise<ExtractedSentence[]> {
  const rels = await relationships(bytes, 'ppt/presentation.xml');
  const ids = Array.from(xml(await zipMember(bytes, 'ppt/presentation.xml')).getElementsByTagNameNS('*', 'sldId'));
  if (ids.length > 500) throw tooLarge('the presentation holds more than 500 slides');
  const out: ExtractedSentence[] = [];
  for (const [i, id] of ids.entries()) {
    const slide = rels.get(id.getAttribute('r:id') || '') || '';
    if (!zipNames(bytes).includes(slide)) continue;
    const parts = [slide, ...Array.from((await relationships(bytes, slide)).values()).filter((t) => t.includes('notesSlide'))];
    for (const part of parts)
      for (const p of Array.from(xml(await zipMember(bytes, part)).getElementsByTagNameNS(DRAWING_NS, 'p'))) {
        const text = Array.from(p.getElementsByTagNameNS(DRAWING_NS, 't'))
          .map((t) => t.textContent || '')
          .join('');
        if (text.trim()) out.push({ text, position: { unit: 'slide', index: i + 1 } });
      }
  }
  return out;
}

/** One unit per non-empty row, cached values joined by `, `; at most 50 sheets. */
async function xlsxRows(bytes: Uint8Array): Promise<ExtractedSentence[]> {
  const rels = await relationships(bytes, 'xl/workbook.xml');
  const sheets = Array.from(xml(await zipMember(bytes, 'xl/workbook.xml')).getElementsByTagNameNS(SHEET_NS, 'sheet'));
  if (sheets.length > 50) throw tooLarge('the workbook holds more than 50 sheets');
  const shared = zipNames(bytes).includes('xl/sharedStrings.xml')
    ? Array.from(xml(await zipMember(bytes, 'xl/sharedStrings.xml')).getElementsByTagNameNS(SHEET_NS, 'si')).map((si) =>
        Array.from(si.getElementsByTagNameNS(SHEET_NS, 't'))
          .filter((t) => (t.parentNode as Element | null)?.localName !== 'rPh')
          .map((t) => t.textContent || '')
          .join(''),
      )
    : [];
  const out: ExtractedSentence[] = [];
  for (const [i, sheet] of sheets.entries()) {
    const part = rels.get(sheet.getAttribute('r:id') || '') || '';
    if (!zipNames(bytes).includes(part)) continue;
    for (const row of Array.from(xml(await zipMember(bytes, part)).getElementsByTagNameNS(SHEET_NS, 'row'))) {
      const values = Array.from(row.getElementsByTagNameNS(SHEET_NS, 'c'))
        .map((c) => {
          const v = c.getElementsByTagNameNS(SHEET_NS, 'v')[0]?.textContent || '';
          const t = c.getAttribute('t');
          if (t === 's') return shared[Number(v)] || '';
          if (t === 'inlineStr') return c.getElementsByTagNameNS(SHEET_NS, 't')[0]?.textContent || '';
          if (t === 'b') return v === '1' ? 'TRUE' : 'FALSE';
          return t === 'e' ? '' : v;
        })
        .map((v) => v.trim())
        .filter(Boolean);
      if (!values.length) continue;
      const text = values.join(', ').replace(/\s+/g, ' ');
      if (text.length > 12 && text.length < 400)
        out.push({ text, position: { unit: 'sheet', index: i + 1, row: Number(row.getAttribute('r')) || undefined } });
    }
  }
  return out;
}

/** Paragraph text of a page parsed without running or fetching anything; script-like and
 * embedded content is dropped, block elements end paragraphs; at most 5 MiB. */
function htmlParagraphs(bytes: Uint8Array): ExtractedSentence[] {
  if (bytes.length > 5 * 1024 * 1024) throw tooLarge('the page is larger than 5 MiB');
  const doc = new DOMParser().parseFromString(new TextDecoder('utf-8').decode(bytes), 'text/html');
  doc.querySelectorAll(DROPPED_HTML).forEach((e) => e.remove());
  const blocks: string[] = [];
  let current = '';
  const flush = () => {
    const text = current.replace(/\s+/g, ' ').trim();
    if (text) blocks.push(text);
    current = '';
  };
  const walk = (node: Node, depth: number) => {
    if (depth > 512) throw tooLarge('the page nests more than 512 elements deep');
    if (node.nodeType === Node.TEXT_NODE) current += node.textContent || '';
    if (node.nodeType !== Node.ELEMENT_NODE && node.nodeType !== Node.DOCUMENT_NODE) return;
    const block = node.nodeType === Node.ELEMENT_NODE && BLOCK_HTML.has((node as Element).localName);
    if (block || (node as Element).localName === 'br') flush();
    node.childNodes.forEach((c) => walk(c, depth + 1));
    if (block) flush();
  };
  walk(doc, 0);
  flush();
  return blocks.map((text, i) => ({ text, position: { unit: 'paragraph', index: i + 1 } }));
}

/** The member names of a ZIP archive, from its central directory. */
function zipNames(bytes: Uint8Array): string[] {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let eocd = -1;
  for (let i = bytes.length - 22; i >= Math.max(0, bytes.length - 65_557); i--)
    if (view.getUint32(i, true) === 0x06054b50) {
      eocd = i;
      break;
    }
  if (eocd < 0) throw unreadable('the document is not a ZIP archive');
  const entries = view.getUint16(eocd + 10, true);
  if (entries > MAX_ARCHIVE_MEMBERS) throw tooLarge('the document holds more than 1,000 archive members');
  const names: string[] = [];
  let at = view.getUint32(eocd + 16, true);
  for (let n = 0; n < entries; n++) {
    if (view.getUint32(at, true) !== 0x02014b50) throw unreadable('the document has a broken ZIP directory');
    const nameLen = view.getUint16(at + 28, true);
    names.push(new TextDecoder().decode(bytes.subarray(at + 46, at + 46 + nameLen)));
    at += 46 + nameLen + view.getUint16(at + 30, true) + view.getUint16(at + 32, true);
  }
  return names;
}

/** One member of a ZIP archive, inflated; the archive may hold at most 1,000 members. */
async function zipMember(bytes: Uint8Array, name: string): Promise<Uint8Array> {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let eocd = -1;
  for (let i = bytes.length - 22; i >= Math.max(0, bytes.length - 65_557); i--)
    if (view.getUint32(i, true) === 0x06054b50) {
      eocd = i;
      break;
    }
  if (eocd < 0) throw unreadable('the Word document is not a ZIP archive');
  const entries = view.getUint16(eocd + 10, true);
  if (entries > MAX_ARCHIVE_MEMBERS) throw tooLarge('the Word document holds more than 1,000 archive members');
  let at = view.getUint32(eocd + 16, true);
  for (let n = 0; n < entries; n++) {
    if (view.getUint32(at, true) !== 0x02014b50) throw unreadable('the Word document has a broken ZIP directory');
    const method = view.getUint16(at + 10, true);
    const size = view.getUint32(at + 20, true);
    const nameLen = view.getUint16(at + 28, true);
    const extraLen = view.getUint16(at + 30, true);
    const commentLen = view.getUint16(at + 32, true);
    const local = view.getUint32(at + 42, true);
    const entryName = new TextDecoder().decode(bytes.subarray(at + 46, at + 46 + nameLen));
    if (entryName === name) {
      const start = local + 30 + view.getUint16(local + 26, true) + view.getUint16(local + 28, true);
      const data = bytes.subarray(start, start + size);
      if (method === 0) return data;
      if (method === 8) return inflate(data, 'deflate-raw');
      throw unreadable('the Word document uses an unsupported compression');
    }
    at += 46 + nameLen + extraLen + commentLen;
  }
  throw unreadable('the Word document has no main part');
}

/** Inflates a stream, stopping past the text limit so a small archive cannot expand without bound. */
async function inflate(data: Uint8Array, format: 'deflate' | 'deflate-raw'): Promise<Uint8Array> {
  const cap = MAX_CHARS * 8;
  const reader = new Blob([new Uint8Array(data)]).stream().pipeThrough(new DecompressionStream(format)).getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.length;
    if (total > cap) {
      await reader.cancel();
      throw tooLarge('the document expands past the text limit');
    }
    chunks.push(value);
  }
  const out = new Uint8Array(total);
  let o = 0;
  for (const c of chunks) {
    out.set(c, o);
    o += c.length;
  }
  return out;
}

/** Text shown by the `Tj` and `TJ` operators of a PDF's content streams, one line per text block. */
async function pdfText(bytes: Uint8Array): Promise<string> {
  const raw = new TextDecoder('latin1').decode(bytes);
  if (!raw.startsWith('%PDF')) throw unreadable('the file is not a PDF document');
  const out: string[] = [];
  const streams = /<<([^]*?)>>\s*stream\r?\n/g;
  let m: RegExpExecArray | null;
  while ((m = streams.exec(raw))) {
    const start = m.index + m[0].length;
    const end = raw.indexOf('endstream', start);
    if (end < 0) break;
    const body = bytes.subarray(start, end);
    const content = /\/FlateDecode/.test(m[1]) ? new TextDecoder('latin1').decode(await inflate(body, 'deflate').catch(() => new Uint8Array())) : raw.slice(start, end);
    for (const block of content.match(/BT[^]*?ET/g) || []) {
      const parts: string[] = [];
      for (const s of block.match(/\((?:\\.|[^\\)])*\)/g) || []) parts.push(unescapePdf(s.slice(1, -1)));
      if (parts.length) out.push(parts.join(''));
    }
    streams.lastIndex = end;
  }
  return out.join('\n');
}

function unescapePdf(s: string): string {
  return s.replace(/\\([nrtbf()\\]|[0-7]{1,3})/g, (_, c: string) => {
    if (/^[0-7]/.test(c)) return String.fromCharCode(parseInt(c, 8));
    return ({ n: '\n', r: '\r', t: '\t', b: '\b', f: '\f' } as Record<string, string>)[c] ?? c;
  });
}
