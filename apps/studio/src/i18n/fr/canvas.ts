import type { canvas as source } from '../en/canvas';
import type { Translation } from '../translation';

export const canvas: Translation<typeof source> = {
  'canvas.cell.awaitingApproval': 'en attente d’approbation',
  'canvas.cell.noData': 'aucune donnée derrière',
  'canvas.cell.bound': '{records} enregistrements · {source} · fraîcheur {fresh}',
  'canvas.source.concepts': ' · {n, plural, one {# concept} other {# concepts}}',
  'canvas.source.awaitingApproval': ' · en attente d’approbation',
  'canvas.company.sub': 'l’entreprise comme un produit · {domains, plural, one {# produit de domaine} other {# produits de domaine}} · {concepts, plural, one {# concept} other {# concepts}}',
  'canvas.company.sources': ' · {n, plural, one {# source} other {# sources}}',
  'canvas.company.bound': ' · {pct} % liés',
  'canvas.domain.sub': 'produit de domaine · {owner} · v{version} · {n, plural, one {# concept} other {# concepts}}',
  'canvas.domain.pending': ' · {n} en attente',
  'canvas.domain.bound': ' · {bound} sur {total} liés',
  'canvas.arrange.lineageTitle': 'Lignée de {label}, disposée',
  'canvas.arrange.lineageText':
    'Déplacée vers une zone dégagée : les ancêtres à gauche, les descendants à droite, les frères et sœurs les uns sous les autres. Le reste du modèle reste intact et à l’écart.',
  'canvas.arrange.domainTitle': '{name}, disposé',
  'canvas.arrange.domainText':
    'Déplacé vers une zone dégagée : {members} concepts de {name} de gauche à droite, {n, plural, one {le # concept} other {les # concepts}} en relation à côté de ce qu’ils touchent. Appuyez sur Disposer sans rien sélectionner pour tout remettre en place.',
  'canvas.arrange.cellTitle': '{label} et ses relations, disposés',
  'canvas.arrange.cellText':
    'Déplacé vers une zone dégagée : {label} au centre, {n, plural, one {son # concept lié} other {ses # concepts liés}} autour, ce qui pointe vers lui à gauche et ce vers quoi il pointe à droite, groupés par produit de domaine. Appuyez sur Disposer sans rien sélectionner pour tout remettre en place.',
};
