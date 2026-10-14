/**
 * Column names on table cells. Each cell of a `table.tbl` carries its column's header text as
 * `data-label`; on a phone a table of five or more columns becomes one card per row, and each
 * cell shows that label in front of its value (the rules in styles/studio.css).
 */
import { useEffect } from 'react';

/** Writes the header text of its column on every body cell of each `table.tbl` under `root`. */
export function labelTableCells(root: ParentNode): void {
  for (const table of root.querySelectorAll<HTMLTableElement>('table.tbl')) {
    const heads: string[] = [];
    for (const th of table.querySelectorAll<HTMLTableCellElement>('thead tr:first-child > th')) {
      for (let i = 0; i < (th.colSpan || 1); i++) heads.push(th.textContent?.trim() ?? '');
    }
    for (const row of table.querySelectorAll<HTMLTableRowElement>(':scope > tbody > tr')) {
      let col = 0;
      for (const cell of row.cells) {
        const label = cell.colSpan > 1 ? '' : (heads[col] ?? '');
        if (cell.getAttribute('data-label') !== label) cell.setAttribute('data-label', label);
        col += cell.colSpan || 1;
      }
    }
  }
}

/** Keeps the cell labels of every table in the document current, once per frame at most. */
export function useTableCellLabels(): void {
  useEffect(() => {
    let frame = 0;
    const run = () => {
      frame = 0;
      labelTableCells(document);
    };
    const observer = new MutationObserver(() => {
      if (!frame) frame = requestAnimationFrame(run);
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    run();
    return () => {
      observer.disconnect();
      if (frame) cancelAnimationFrame(frame);
    };
  }, []);
}
