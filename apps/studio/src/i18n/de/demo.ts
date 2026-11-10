import type { demo as source } from '../en/demo';
import type { Translation } from '../translation';

export const demo: Translation<typeof source> = {
  'demo.button.label': 'Ein Demo-Gehirn wachsen lassen',
  'demo.button.start': 'Ein Demo-Gehirn wachsen lassen: eine große Beispielontologie, auf die Leinwand gezeichnet, nie gespeichert',
  'demo.button.stop': 'Das Demo-Gehirn anhalten (Esc)',
  'demo.bar.grown': 'Das Demo-Gehirn ist gewachsen: {n} Konzepte.',
};
