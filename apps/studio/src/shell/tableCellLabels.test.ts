import { describe, expect, it } from 'vitest';

import { labelTableCells } from './tableCellLabels';

const table = (html: string): HTMLElement => {
  const root = document.createElement('div');
  root.innerHTML = html;
  return root;
};

describe('labelTableCells', () => {
  it('writes each column header on the cells of its column', () => {
    const root = table(
      '<table class="tbl"><thead><tr><th>Entity</th><th>Kind</th><th></th></tr></thead>' +
        '<tbody><tr><td>Customer</td><td>concept</td><td class="act"></td></tr></tbody></table>',
    );
    labelTableCells(root);
    const labels = [...root.querySelectorAll('td')].map((td) => td.getAttribute('data-label'));
    expect(labels).toEqual(['Entity', 'Kind', '']);
  });

  it('gives a cell spanning several columns no label and keeps counting after it', () => {
    const root = table(
      '<table class="tbl"><thead><tr><th>A</th><th>B</th><th>C</th></tr></thead>' +
        '<tbody><tr><td colspan="2">wide</td><td>c</td></tr><tr><td colspan="3">Nothing matches.</td></tr></tbody></table>',
    );
    labelTableCells(root);
    const labels = [...root.querySelectorAll('td')].map((td) => td.getAttribute('data-label'));
    expect(labels).toEqual(['', 'C', '']);
  });

  it('leaves tables without the tbl class alone', () => {
    const root = table('<table><thead><tr><th>A</th></tr></thead><tbody><tr><td>a</td></tr></tbody></table>');
    labelTableCells(root);
    expect(root.querySelector('td')?.hasAttribute('data-label')).toBe(false);
  });
});
