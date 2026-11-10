import type { canvas as source } from '../en/canvas';
import type { Translation } from '../translation';

export const canvas: Translation<typeof source> = {
  'canvas.cell.awaitingApproval': 'wartet auf Genehmigung',
  'canvas.cell.noData': 'keine Daten dahinter',
  'canvas.cell.bound': '{records} Datensätze · {source} · Stand {fresh}',
  'canvas.source.concepts': ' · {n, plural, one {# Konzept} other {# Konzepte}}',
  'canvas.source.awaitingApproval': ' · wartet auf Genehmigung',
  'canvas.company.sub': 'das Unternehmen als Produkt · {domains, plural, one {# Domänenprodukt} other {# Domänenprodukte}} · {concepts, plural, one {# Konzept} other {# Konzepte}}',
  'canvas.company.sources': ' · {n, plural, one {# Quelle} other {# Quellen}}',
  'canvas.company.bound': ' · {pct} % angebunden',
  'canvas.domain.sub': 'Domänenprodukt · {owner} · v{version} · {n, plural, one {# Konzept} other {# Konzepte}}',
  'canvas.domain.pending': ' · {n} ausstehend',
  'canvas.domain.bound': ' · {bound} von {total} angebunden',
  'canvas.arrange.lineageTitle': 'Abstammung von {label}, angeordnet',
  'canvas.arrange.lineageText':
    'In einen freien Bereich verschoben: Vorfahren links, Nachkommen rechts, Geschwister untereinander. Der Rest des Modells bleibt unberührt und aus dem Weg.',
  'canvas.arrange.domainTitle': '{name}, angeordnet',
  'canvas.arrange.domainText':
    'In einen freien Bereich verschoben: {members} Konzepte von {name} von links nach rechts, {n, plural, one {das # verbundene Konzept} other {die # verbundenen Konzepte}} neben dem, was sie berühren. Drücken Sie Anordnen ohne Auswahl, um alles zurückzusetzen.',
  'canvas.arrange.cellTitle': '{label} und seine Beziehungen, angeordnet',
  'canvas.arrange.cellText':
    'In einen freien Bereich verschoben: {label} in der Mitte, {n, plural, one {sein # verknüpftes Konzept} other {seine # verknüpften Konzepte}} darum herum, was darauf zeigt links und worauf es zeigt rechts, nach Domänenprodukt gruppiert. Drücken Sie Anordnen ohne Auswahl, um alles zurückzusetzen.',
};
