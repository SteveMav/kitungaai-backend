# Product

## Register

product

## Users

Les caissiers et gestionnaires d'un magasin local de composants électroniques. Ils utilisent l'interface pendant le service, souvent debout ou en alternant rapidement entre le panier physique et l'écran. Leur tâche principale est de comprendre ce que le panier contient, corriger une détection si nécessaire, encaisser, puis surveiller un stock simple.

## Product Purpose

Kitunga relie les paniers physiques équipés d'une Raspberry Pi au catalogue Django. L'application montre les ajouts et retraits détectés, sélectionne un panier à la caisse grâce à sa matrice, permet une vérification humaine, puis enregistre la vente et décrémente le stock. Le succès se mesure à une chose : un caissier comprend l'état du panier sans explication technique et ne valide jamais une vente ambiguë.

## Brand Personality

Claire, fiable, directe. L'interface doit inspirer le calme d'un bon outil de caisse et rendre la technologie invisible derrière le travail à accomplir.

## Anti-references

- Aucun code-barres dans le produit ou l'interface.
- Aucun tableau de bord rempli de graphiques, métriques fictives ou cartes décoratives.
- Aucun style futuriste sombre, néon, verre dépoli ou gradient violet de démonstration IA.
- Aucune animation gratuite, jargon technique exposé au caissier ou navigation expérimentale.

## Design Principles

1. Le panier avant la technologie : montrer les articles, quantités, prix et état avant les détails matériels.
2. Une décision principale par écran : surveiller, corriger ou confirmer.
3. La caisse reste humaine : une détection ou un scan sélectionne, mais ne facture jamais seul.
4. Les états doivent se lire en un regard : connecté, à vérifier, terminé, stock faible.
5. Chaque écran vide explique la prochaine action réelle.

## Accessibility & Inclusion

Viser WCAG 2.2 AA : contraste suffisant, navigation clavier complète, zones tactiles d'au moins 44 px, focus visible, libellés textuels en plus de la couleur et respect de la préférence de mouvement réduit.
