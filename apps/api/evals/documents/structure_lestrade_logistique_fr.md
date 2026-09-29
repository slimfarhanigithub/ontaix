# Manuel des procédures d'exploitation

Lestrade Logistique est une organisation fictive et ce manuel a été rédigé comme support d'évaluation.

Version 4.2 – Diffusion interne – Direction des opérations

## Objet du manuel

Ce manuel décrit les procédures d'exploitation communes à l'ensemble des sites de Lestrade Logistique,
prestataire logistique pour le compte de clients de la distribution spécialisée, de la cosmétique
et des pièces détachées industrielles. Il s'impose à tout le personnel d'exploitation, intérimaires
compris, et prévaut sur les modes opératoires locaux en cas de contradiction. Toute dérogation est
validée par écrit par la direction des opérations.

L'activité de Lestrade Logistique s'organise autour de la réception, du stockage, de la préparation de commandes, de l'expédition, de la gestion des litiges et de l'inventaire.

## Réseau d'entrepôts

Lestrade Logistique exploite quatre entrepôts, dont les caractéristiques principales figurent dans le tableau ci-dessous.

| Code | Entrepôt | Surface | Activité dominante |
|---|---|---|---|
| LYO | Entrepôt de Corbas | 42 000 m² | Distribution spécialisée |
| FOS | Entrepôt de Fos-sur-Mer | 36 000 m² | Import conteneurisé |
| LIL | Entrepôt de Lesquin | 28 000 m² | Cosmétique et parfumerie |
| ORL | Entrepôt de Saran | 31 000 m² | Pièces détachées |

L'entrepôt de Fos-sur-Mer dispose d'une zone sous douane réservée aux marchandises en suspension de droits.

## Réception

La réception couvre l'ensemble des opérations comprises entre l'arrivée du camion au poste de
garde et la mise à disposition de la marchandise dans le stock disponible. Elle est placée sous
la responsabilité du chef d'équipe réception de chaque site, qui répond de la conformité des
saisies dans le WMS. La réception comprend

- Prise de rendez-vous
- Déchargement
- Contrôle à réception

### Prise de rendez-vous

Tout transporteur livrant un entrepôt de Lestrade Logistique doit réserver un créneau sur le portail de prise de rendez-vous au plus tard quarante-huit heures avant sa présentation, en indiquant le numéro de commande d'achat, le nombre de palettes et la nature des marchandises; un camion qui se présente sans rendez-vous peut être refusé ou mis en attente jusqu'au premier créneau libre, et les frais d'immobilisation qui en résultent ne sont en aucun cas refacturés au client déposant, sauf accord écrit préalable du responsable de site concerné.

### Déchargement

Le déchargement est réalisé par un cariste habilité, sur le quai affecté par le chef d'équipe. Les palettes sont déposées dans la zone tampon de réception et ne doivent jamais bloquer une allée de circulation.

### Contrôle à réception

Le contrôle à réception se compose de

1. Contrôle quantitatif du nombre de palettes et de colis livrés
2. Contrôle qualitatif de l'état des emballages et des dates limites
3. Émission des réserves sur le document du transporteur en cas d'anomalie
4. Saisie dans le WMS des quantités effectivement reçues

L'émission des réserves produit une fiche de non-conformité, transmise au service client dans la journée.

La fiche de non-conformité comprend les photographies des colis endommagés, prises avant tout déplacement de la marchandise et horodatées par le terminal portable, ainsi que le numéro de lot, le nom du chauffeur et l'immatriculation du véhicule; elle est archivée pendant trois ans au moins, y compris lorsque le client renonce à toute réclamation, afin que le service qualité puisse établir les statistiques de casse par transporteur, par client et par famille de produits lors de la revue trimestrielle.

## Stockage

Le stockage commence au moment où la palette quitte la zone tampon de réception et s'achève
lorsque la marchandise est prélevée pour une commande. Les emplacements sont gérés exclusivement
dans le WMS, et aucun mouvement physique ne peut être réalisé sans ordre de mouvement édité par
le système. Le stockage comprend

- Adressage
- Réapprovisionnement des emplacements
- Gestion des marchandises dangereuses, pour les aérosols, les liquides inflammables et les produits relevant de la réglementation des installations classées

### Adressage

L'adressage dynamique est un type d'adressage réservé aux références à forte rotation. L'adressage fixe est un type d'adressage utilisé pour les pièces détachées et les articles encombrants.

Le choix entre les deux modes est arrêté référence par référence lors de l'ouverture du dossier client, en tenant compte de la rotation constatée sur les six derniers mois, du volume unitaire, de la fragilité et des contraintes de compatibilité entre produits; il est revu au moins une fois par an avec le client, et plus souvent lorsque le taux de remplissage d'une cellule dépasse quatre-vingt-dix pour cent pendant plus de deux semaines consécutives ou lorsque le client annonce une opération promotionnelle.

### Marchandises dangereuses

Dans le cadre de la gestion des marchandises dangereuses, chaque site tient un registre des matières dangereuses mis à jour à chaque entrée et à chaque sortie. Ce registre est présenté sans délai à toute demande des services d'incendie et de secours.

## Préparation de commandes

La préparation de commandes transforme les commandes transmises par les clients en colis prêts à
expédier, dans le respect des délais contractuels. Les commandes reçues avant l'heure de coupure
sont préparées le jour même. La préparation de commandes comprend

- Cycle de préparation
- Traitement des commandes urgentes, pour toute commande reçue après l'heure de coupure et confirmée par le client comme prioritaire

### Cycle de préparation

Le cycle de préparation se compose des étapes décrites dans le tableau ci-dessous

| N° | Étape | Responsable | Livrable |
|---|---|---|---|
| 1 | Lancement de la vague | Pilote de flux | Liste de prélèvement |
| 2 | Prélèvement | Préparateur | Bac de préparation |
| 3 | Contrôle de préparation | Contrôleur qualité | Bon de contrôle |
| 4 | Emballage | Opérateur d'emballage | Colis fermé |
| 5 | Étiquetage | Opérateur d'emballage | Étiquette transporteur |

Le contrôle de préparation vérifie la liste de prélèvement ligne par ligne.

### Commandes urgentes

Le traitement des commandes urgentes est déclenché uniquement sur demande écrite du client, transmise par le portail ou par courriel au pilote de flux, et donne lieu à une facturation spécifique prévue au contrat; le pilote de flux peut alors interrompre une vague en cours, affecter un préparateur dédié et réserver un créneau de départ supplémentaire auprès du transporteur, à condition que la sécurité des opérateurs et la qualité de la préparation ne soient à aucun moment compromises par cette accélération.

## Expédition

L'expédition regroupe les opérations réalisées entre la dépose du colis fermé en zone de
départ et la remise de la marchandise au transporteur. Elle se termine par la signature du
chauffeur, qui transfère la garde de la marchandise. L'expédition comprend

- Consolidation des colis
- Chargement
- Émission des documents de transport

L'émission des documents de transport produit la lettre de voiture et le bordereau de remise.

Le chargement exige la signature du bordereau de remise par le chauffeur.

Aucun camion ne quitte le quai tant que le chef de quai n'a pas vérifié la concordance entre le nombre de supports chargés et le nombre de supports déclarés, contrôlé l'arrimage, le calage et la fermeture des portes, et scanné le plomb de sécurité lorsque le client en exige un; toute différence constatée est consignée sur le bordereau et signalée au service client avant le départ du véhicule, faute de quoi elle ne pourra plus être opposée au transporteur en cas de réclamation ultérieure.

## Gestion des litiges

La gestion des litiges traite toute contestation relative à une livraison, qu'elle provienne
d'un client, d'un destinataire final ou d'un transporteur. Elle est pilotée par le service client
du site concerné, avec l'appui du responsable qualité. La gestion des litiges comprend

- Traitement des réclamations clients
- Litiges transporteurs

L'émission des réserves alimente le traitement des réclamations clients lorsque le client conteste la livraison.

### Traitement des réclamations clients

1. Enregistrement de la réclamation dans l'outil de suivi
2. Analyse des causes
3. Proposition d'indemnisation
4. Clôture du litige

L'analyse des causes consulte la fiche de non-conformité et les enregistrements vidéo du quai. L'analyse des causes produit un rapport d'analyse, signé par le responsable qualité du site.

Le rapport d'analyse comprend un plan d'actions correctives, qui désigne pour chaque action un responsable nommément identifié, une échéance et un indicateur de résultat mesurable, et qui est présenté au client lors de la revue mensuelle de performance; lorsque la même cause est constatée plus de trois fois sur un trimestre, le responsable de site ouvre une analyse approfondie et en informe la direction des opérations, qui peut décider d'un audit croisé réalisé par un autre entrepôt du réseau.

La proposition d'indemnisation s'appuie sur la lettre de voiture et sur les conditions contractuelles de responsabilité.

### Litiges transporteurs

Les litiges transporteurs portent sur les avaries, pertes et retards imputables au transporteur, et sont instruits par le service client sur la base des réserves émises à réception ou des anomalies constatées au départ; le délai de confirmation des réserves par lettre recommandée est de trois jours ouvrables, hors jours fériés, et tout dépassement de ce délai fait perdre à Lestrade Logistique le droit d'agir contre le transporteur, ce qui engage alors directement la responsabilité du site concerné vis-à-vis du client.

## Inventaire

L'inventaire garantit la concordance entre le stock physique et le stock informatique, sur
laquelle repose la facturation des prestations de stockage. L'inventaire comprend

- Inventaire tournant
- Inventaire annuel

Le réapprovisionnement des emplacements déclenche un inventaire tournant sur l'emplacement vidé.

### Inventaire annuel

L'inventaire annuel se déroule le dernier week-end de l'exercice du client, entrepôt fermé et
flux arrêtés. Les activités et les responsabilités sont réparties selon la matrice RACI
ci-dessous, que le responsable de site transmet au client au moins un mois à l'avance.

| Activité | Chef d'équipe | Responsable de site | Contrôleur de gestion | Client |
|---|---|---|---|---|
| Préparation de l'inventaire | C | A | R | I |
| Comptage | R | A | I | I |
| Recomptage des écarts | R | A | C | I |
| Validation des écarts | I | R | A | C |
| Ajustement des stocks | R | A | C | I |

La validation des écarts produit le procès-verbal d'inventaire, cosigné par le client.

Le procès-verbal d'inventaire comprend l'état des écarts valorisés, établi au prix de revient communiqué par le client, ainsi que la liste des références recomptées, l'identité des équipes de comptage et les réserves éventuelles formulées par le client; il est transmis au contrôleur de gestion dans les cinq jours ouvrables suivant la clôture, et aucune facture de stockage ne peut être émise pour la période concernée tant que ce document n'a pas été signé par les deux parties.

L'ajustement des stocks met à jour le registre des matières dangereuses pour les références concernées.
