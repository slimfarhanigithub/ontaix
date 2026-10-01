/**
 * Setting-row texts the Studio adds to the reference's admin pages: a description for each row
 * the reference leaves without one, keyed by the row's title, and the Appearance page's Skip
 * animation row. Plain data, shared by the pages and the screenshot harness, which adds the same
 * texts to the reference page so the rest of each page still compares pixel for pixel.
 */

/** Descriptions of the Tenant settings rows the reference leaves empty, by row title. */
export const ADDED_DESCRIPTIONS: Record<string, string> = {
  'Approval required for every change': 'Every change is a proposal that an approver accepts or rejects. Always on.',
  'Several companies in one view': 'Show and teach more than one company on the canvas.',
  'Show the relationship legend': 'The key to the line styles, at the bottom right of the canvas.',
};

/** The Appearance page's Motion section: its heading, the row title and the row description. */
export const SKIP_ANIMATION_ROW = {
  heading: 'Motion',
  title: 'Skip animation',
  desc: 'New cells appear at once, without the division animation. Only for you, in this browser. Shortcut S.',
} as const;
