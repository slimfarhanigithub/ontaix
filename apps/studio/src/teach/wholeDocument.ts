/**
 * Whole-document reading: the API maps a stored import into one tree of proposals in an
 * asynchronous job. The Studio starts the job, follows it by polling every 5 seconds (and at once
 * on each `extraction.changed` event of the job), shows its progress in the caption, and submits
 * every draft of the result. The tree is then reviewed in the changes panel.
 */
import { api } from '../api/client';
import { liveEvents } from '../api/events';
import type { DocumentExtraction, ImportResult } from '../api/types';
import { store } from '../store/store';

/** How often a running job is read. */
export const POLL_MS = 5000;

const FINAL = new Set<DocumentExtraction['state']>(['succeeded', 'failed', 'cancelled']);

/** What became of a whole-document reading; `unavailable` means the caller falls back to sentence by sentence. */
export type WholeDocumentOutcome = 'proposed' | 'nothing' | 'unavailable';

export async function readWholeDocument(imported: ImportResult, companyId: string): Promise<WholeDocumentOutcome> {
  const kicker = `Reading ${imported.fileName}`;
  let job: DocumentExtraction;
  try {
    job = await api.startDocumentExtraction(imported.importId, companyId);
    while (!FINAL.has(job.state)) {
      store.caption(kicker, progressText(job));
      await nextRead(job.id);
      job = await api.getDocumentExtraction(job.id);
    }
  } catch {
    store.caption(kicker, 'Whole-document reading is not available');
    return 'unavailable';
  }
  if (job.state === 'failed' && job.failureReason === 'no_drafts') {
    store.caption(kicker, `Nothing to propose from ${imported.fileName}`);
    return 'nothing';
  }
  if (job.state !== 'succeeded') {
    store.caption(kicker, 'Whole-document reading is not available');
    return 'unavailable';
  }
  try {
    const result = await api.getDocumentExtractionResult(job.id);
    if (!result.drafts.length) {
      store.caption(kicker, `Nothing to propose from ${imported.fileName}`);
      return 'nothing';
    }
    const made = await api.proposeDocumentExtraction(
      job.id,
      result.drafts.map((_, i) => i),
    );
    await store.refreshProposals();
    store.caption(kicker, `${made.length} proposals from ${imported.fileName}`);
    return 'proposed';
  } catch (err) {
    store.refused(err);
    store.caption(kicker, `Nothing to propose from ${imported.fileName}`);
    return 'nothing';
  }
}

/** The caption text of a running job. */
export function progressText(job: DocumentExtraction): string {
  return `Outline ${job.outlineChunksDone} of ${job.chunks} · sections ${job.sectionChunksDone} of ${job.chunks}`;
}

/** Waits for the next poll, or less when an event about the job arrives. */
function nextRead(jobId: string): Promise<void> {
  return new Promise((resolve) => {
    const done = () => {
      clearTimeout(timer);
      unsubscribe();
      resolve();
    };
    const timer = setTimeout(done, POLL_MS);
    const unsubscribe = liveEvents.subscribe((e) => {
      const extraction = e.payload.extraction as DocumentExtraction | undefined;
      if (e.type === 'extraction.changed' && extraction?.id === jobId) done();
    });
  });
}
