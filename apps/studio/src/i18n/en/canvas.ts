/** English source strings of the canvas area: the chrome drawn under cells and over regions, and the Arrange captions. */
export const canvas = {
  'canvas.cell.awaitingApproval': 'awaiting approval',
  'canvas.cell.noData': 'no data behind it',
  'canvas.cell.bound': '{records} records · {source} · fresh {fresh}',
  'canvas.source.concepts': ' · {n, plural, one {# concept} other {# concepts}}',
  'canvas.source.awaitingApproval': ' · awaiting approval',
  'canvas.company.sub': 'business as a product · {domains, plural, one {# domain product} other {# domain products}} · {concepts, plural, one {# concept} other {# concepts}}',
  'canvas.company.sources': ' · {n, plural, one {# source} other {# sources}}',
  'canvas.company.bound': ' · {pct} % bound',
  'canvas.domain.sub': 'domain product · {owner} · v{version} · {n, plural, one {# concept} other {# concepts}}',
  'canvas.domain.pending': ' · {n} pending',
  'canvas.domain.bound': ' · {bound} of {total} bound',
  'canvas.arrange.lineageTitle': 'Lineage of {label}, arranged',
  'canvas.arrange.lineageText':
    'Moved to a clear area: ancestors on the left, descendants to the right, siblings one under another. The rest of the model is untouched and out of the way.',
  'canvas.arrange.domainTitle': '{name}, arranged',
  'canvas.arrange.domainText':
    'Moved to a clear area: {members} concepts of {name} from left to right, the {n, plural, one {# concept} other {# concepts}} it relates to beside what they touch. Press Arrange with nothing selected to put everything back.',
  'canvas.arrange.cellTitle': '{label} and its relations, arranged',
  'canvas.arrange.cellText':
    'Moved to a clear area: {label} in the middle, its {n, plural, one {# linked concept} other {# linked concepts}} around it, what points to it on the left and what it points to on the right, grouped by domain product. Press Arrange with nothing selected to put everything back.',
};
