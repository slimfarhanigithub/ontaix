/**
 * Document extraction of the in-browser mock, mirroring `POST /import/sentences`: file name and
 * media type checks, the size, text and sentence limits, and sentence splitting. Plain text,
 * Markdown, CSV and JSON are decoded as UTF-8; Word documents are read from their ZIP archive
 * with no DTD; PDF text is read from its literal text operators, a best effort for simple files.
 * Sentences are split the way reference/ontaix-studio-reference.html line 900 (`sentencesOf`)
 * does, per paragraph when the paragraph is known, and a sentence longer than 399 characters is cut
 * into pieces the way the API cuts it, so no text is lost to the length limit.
 */
import type { DocumentPosition, ImportMediaType } from '../types';

export const IMPORT_MAX_BYTES = 10 * 1024 * 1024;
const MAX_CHARS = 2_000_000;
const MAX_SENTENCES = 2000;
const MAX_ARCHIVE_MEMBERS = 1000;
const MAX_FILE_NAME_BYTES = 1020;
const MAX_FILE_NAME_CHARS = 255;
const DOCX: ImportMediaType = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
const WORD_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main';

const BY_EXTENSION: Record<string, ImportMediaType> = {
  txt: 'text/plain',
  md: 'text/markdown',
  markdown: 'text/markdown',
  csv: 'text/csv',
  json: 'application/json',
  docx: DOCX,
  pdf: 'application/pdf',
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
  /** Pieces of text left out of `sentences`. */
  skipped: number;
}

const MIN_SENTENCE_CHARS = 13;
const MAX_SENTENCE_CHARS = 399;
// Clause boundaries a long sentence is cut after, in order of preference.
const CLAUSE_ENDS = [/[;:]\s/g, /,\s(?=(?:and|or|but|so|yet|nor|while|whereas|because|which|including)\b)/g];

/** Splits text into sentences of 13 to 399 characters; a longer sentence is cut into pieces. */
export function sentencesOf(text: string): string[] {
  return piecesOf(text).filter((x) => x.length >= MIN_SENTENCE_CHARS);
}

/** The pieces of text `sentencesOf` leaves out as shorter than 13 characters that hold a letter or a digit. */
export function skippedOf(text: string): number {
  return piecesOf(text).filter((x) => x.length < MIN_SENTENCE_CHARS && /[\p{L}\p{N}]/u.test(x)).length;
}

function piecesOf(text: string): string[] {
  return text
    .replace(/\s+/g, ' ')
    .split(/(?<=[.!?])\s+|\n+/)
    .flatMap((x) => fit(x.trim()));
}

/** `sentence` in pieces of at most 399 characters, each cut after a clause boundary, else at the
 * last space, else at 399 characters; only the whitespace at a cut is dropped. */
function fit(sentence: string): string[] {
  const pieces: string[] = [];
  let start = 0;
  const end = sentence.length;
  while (end - start > MAX_SENTENCE_CHARS) {
    // Both sides of a cut keep at least 13 characters once the space at the cut is dropped.
    const limit = Math.min(MAX_SENTENCE_CHARS, end - start - MIN_SENTENCE_CHARS - 1);
    const window = sentence.slice(start, start + limit + 1);
    let cut = 0;
    for (const pattern of CLAUSE_ENDS) {
      const ends = Array.from(window.matchAll(pattern), (m) => m.index + 1).filter(
        (e) => e >= MIN_SENTENCE_CHARS && e <= limit,
      );
      if (ends.length) {
        cut = ends[ends.length - 1];
        break;
      }
    }
    if (!cut) {
      const space = window.lastIndexOf(' ');
      cut = space >= MIN_SENTENCE_CHARS ? space : limit;
    }
    pieces.push(sentence.slice(start, start + cut).trim());
    start += cut;
    while (start < end && /\s/.test(sentence[start])) start++;
  }
  if (start < end) pieces.push(sentence.slice(start, end));
  return pieces;
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
  throw new ExtractRefusal(415, 'unsupported_media_type', 'text, Markdown, CSV, JSON, Word and PDF documents are supported');
}

export async function extractDocument(rawName: string, contentType: string, bytes: Uint8Array): Promise<Extracted> {
  const fileName = checkedFileName(rawName);
  const mediaType = mediaTypeOf(fileName, contentType);
  if (bytes.length > IMPORT_MAX_BYTES) throw tooLarge('the document is larger than 10 MiB');
  const mismatch = contentMismatch(bytes, mediaType);
  if (mismatch) throw new ExtractRefusal(415, 'unsupported_media_type', mismatch);
  const units = await unitsOf(mediaType, bytes);
  let chars = 0;
  const sentences: ExtractedSentence[] = [];
  let skipped = 0;
  for (const unit of units) {
    chars += unit.text.length;
    if (chars > MAX_CHARS) throw tooLarge('the document holds more than 2,000,000 characters of text');
    for (const text of sentencesOf(unit.text)) sentences.push({ text, position: unit.position });
    skipped += skippedOf(unit.text);
    if (sentences.length > MAX_SENTENCES) throw tooLarge('the document holds more than 2,000 sentences');
  }
  return { fileName, mediaType, sentences, skipped };
}

/** Why the bytes are not a file of the media type: a Word document is a ZIP archive, a PDF
 * carries its signature in its first kilobyte, and a text type is UTF-8 that is neither. */
export function contentMismatch(bytes: Uint8Array, mediaType: ImportMediaType): string | null {
  const zip = bytes[0] === 0x50 && bytes[1] === 0x4b && bytes[2] === 0x03 && bytes[3] === 0x04;
  const pdf = new TextDecoder('latin1').decode(bytes.subarray(0, 1024)).includes('%PDF-');
  if (mediaType === DOCX) return zip ? null : 'the file is not a Word document';
  if (mediaType === 'application/pdf') return pdf ? null : 'the file is not a PDF';
  if (zip || pdf) return 'the file is a Word or PDF document, not text';
  try {
    new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  } catch {
    return 'the file is not UTF-8 text';
  }
  return null;
}

const tooLarge = (detail: string) => new ExtractRefusal(413, 'payload_too_large', detail);
const unreadable = (detail: string) => new ExtractRefusal(422, 'validation_failed', detail);

async function unitsOf(mediaType: ImportMediaType, bytes: Uint8Array): Promise<ExtractedSentence[]> {
  if (mediaType === DOCX) return docxParagraphs(bytes);
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
