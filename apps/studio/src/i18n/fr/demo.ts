import type { demo as source } from '../en/demo';
import type { Translation } from '../translation';

export const demo: Translation<typeof source> = {
  'demo.button.label': 'Faire pousser un cerveau de démonstration',
  'demo.button.start': 'Faire pousser un cerveau de démonstration : une grande ontologie d’exemple dessinée sur le canevas, jamais enregistrée',
  'demo.button.stop': 'Arrêter le cerveau de démonstration (Échap)',
  'demo.bar.grown': 'Le cerveau de démonstration a poussé : {n} concepts.',
};
