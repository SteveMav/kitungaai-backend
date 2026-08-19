# Spécification UI/UX — Kitunga

## Décision

L'interface est un produit interne de magasin, pas une vitrine marketing. Elle utilise Django Templates, CSS et JavaScript natif, comme prévu par l'architecture. La densité est moyenne, la variance visuelle modérée et le mouvement limité aux retours d'état.

## Parcours principal

1. Le gestionnaire crée les produits, leur prix, leur stock et les labels reconnus par la caméra.
2. La Raspberry Pi ouvre une session et envoie des événements stables d'ajout ou de retrait.
3. L'écran **Paniers** montre le contenu vivant de chaque panier physique.
4. Le scan de la matrice place le panier dans la file **Caisse** et le verrouille.
5. Le caissier vérifie ou corrige les quantités, choisit le statut de paiement et confirme.
6. Django crée la vente, décrémente le stock et demande au panier physique de se réinitialiser.

## Architecture d'information

- **Vue d'ensemble** : situations nécessitant une attention et raccourcis vers le travail.
- **Paniers** : liste des paniers à gauche, contenu détaillé du panier sélectionné à droite.
- **Caisse** : file des paniers à vérifier, correction des lignes et confirmation de vente.
- **Stock** : table produits, recherche, création, modification et ajustement audité.
- **Administration** : configuration avancée des appareils et labels, via Django Admin.

## Comportements par état

- **Chargement** : blocs squelettes uniquement pour les contenus actualisés en JavaScript.
- **Vide** : message expliquant l'action matérielle ou administrative attendue.
- **Erreur** : bandeau local avec explication et possibilité de réessayer.
- **Hors ligne** : l'état du panier reste visible, accompagné de la dernière activité connue.
- **Conflit** : recharge du panier et message demandant de vérifier la version courante.
- **Succès** : confirmation courte, vente identifiée, puis retour à la file.

## Règles responsives

- À partir de `1120px`, le suivi et la caisse utilisent une vue maître/détail.
- Entre `760px` et `1119px`, le rail est compact et les panneaux s'empilent si nécessaire.
- Sous `760px`, la navigation devient une barre supérieure, les tableaux deviennent des listes structurées et les actions principales restent accessibles sans défilement horizontal.

## Accessibilité

- Objectif WCAG 2.2 AA.
- Focus clavier visible sur chaque contrôle.
- Cibles interactives d'au moins `44 × 44px`.
- Libellés explicites, messages associés aux champs et états non dépendants de la seule couleur.
- Prix et quantités annoncés dans un ordre logique ; mises à jour en direct dans une zone `aria-live` discrète.
- Animations désactivées avec `prefers-reduced-motion`.

## Critères de handoff

- Aucune occurrence fonctionnelle de code-barres.
- Un utilisateur authentifié peut parcourir vue d'ensemble, paniers, caisse et stock.
- Le contenu d'un panier est compréhensible sans connaître l'API ou le matériel.
- La confirmation d'une vente nécessite une action explicite du caissier.
- Toutes les vues ont un état vide, une gestion d'erreur et un comportement mobile.
