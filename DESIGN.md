---
name: Kitunga
description: Interface de caisse et de suivi des paniers physiques
colors:
  paper: "oklch(97.5% 0.009 82)"
  surface: "oklch(99% 0.004 82)"
  ink: "oklch(24% 0.018 58)"
  muted: "oklch(52% 0.018 58)"
  line: "oklch(88% 0.014 75)"
  copper: "oklch(58% 0.145 43)"
  copper-deep: "oklch(49% 0.14 41)"
  olive: "oklch(52% 0.105 137)"
  amber-soft: "oklch(93% 0.055 87)"
  danger: "oklch(52% 0.17 28)"
typography:
  title:
    fontFamily: '"Segoe UI Variable", "Aptos", system-ui, sans-serif'
    fontSize: "1.5rem"
    fontWeight: 680
    lineHeight: 1.2
  body:
    fontFamily: '"Segoe UI Variable", "Aptos", system-ui, sans-serif'
    fontSize: "0.9375rem"
    fontWeight: 450
    lineHeight: 1.5
  label:
    fontFamily: '"Segoe UI Variable", "Aptos", system-ui, sans-serif'
    fontSize: "0.75rem"
    fontWeight: 650
    lineHeight: 1.3
    letterSpacing: "0.04em"
rounded:
  sm: "6px"
  md: "10px"
  lg: "14px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.copper}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    padding: "11px 16px"
  button-primary-hover:
    backgroundColor: "{colors.copper-deep}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    padding: "11px 16px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "10px 12px"
---

# Design System: Kitunga

## 1. Overview

**Creative North Star: "Le comptoir bien rangé"**

Kitunga ressemble à un outil de magasin fiable : des surfaces chaudes proches du papier, une structure nette et des données faciles à comparer. Le contenu du panier occupe toujours l'espace principal ; les détails techniques restent secondaires et traduits en états compréhensibles.

Le système rejette les codes visuels de démonstration IA : pas de verre, de néon, de gradients décoratifs ou de mosaïque de cartes. La personnalité vient de la composition, de l'accent cuivre et d'une typographie fonctionnelle.

**Key Characteristics:**

- Densité moyenne et hiérarchie calme.
- Séparateurs et fonds tonals avant les ombres.
- Accent cuivre réservé aux actions et sélections.
- États toujours exprimés par un libellé et une couleur.

## 2. Colors

Une palette de comptoir éclairé : papier chaud, encre profonde, cuivre pour agir et olive pour confirmer.

### Primary

- **Cuivre actif** (`oklch(58% 0.145 43)`): actions principales, sélection courante et focus.

### Neutral

- **Papier chaud** (`oklch(97.5% 0.009 82)`): arrière-plan général.
- **Surface claire** (`oklch(99% 0.004 82)`): zones de travail et champs.
- **Encre** (`oklch(24% 0.018 58)`): texte principal.
- **Trait sable** (`oklch(88% 0.014 75)`): séparateurs et contours.

**The One Voice Rule.** Le cuivre couvre moins de 10 % d'un écran et ne sert jamais de décoration.

## 3. Typography

**Display Font:** Segoe UI Variable (avec Aptos et system-ui)
**Body Font:** Segoe UI Variable (avec Aptos et system-ui)
**Label/Mono Font:** ui-monospace pour les identifiants matériels uniquement

**Character:** Une seule famille native, lisible et rapide à charger. Les chiffres utilisent les variantes tabulaires pour que prix et quantités restent alignés.

### Hierarchy

- **Headline** (680, 1.5rem, 1.2): titre de page.
- **Title** (650, 1rem, 1.35): titre de section ou produit.
- **Body** (450, 0.9375rem, 1.5): contenu courant.
- **Label** (650, 0.75rem, 0.04em): micro-libellés courts, rarement en capitales.

**The Plain Language Rule.** Les libellés décrivent l'action métier, jamais le protocole technique.

## 4. Elevation

Le système est plat par défaut. La profondeur vient des fonds tonals et des traits de 1 px. Une ombre légère est réservée aux menus flottants et aux dialogues.

### Shadow Vocabulary

- **Flottant** (`box-shadow: 0 12px 32px oklch(24% 0.018 58 / 0.12)`): dialogues et menus uniquement.

**The Flat-By-Default Rule.** Une zone permanente ne reçoit pas d'ombre.

## 5. Components

### Buttons

- **Shape:** légèrement arrondie (`6px`), hauteur minimale `44px`.
- **Primary:** cuivre actif, texte clair, `11px 16px`.
- **Hover / Focus:** cuivre profond au survol ; anneau de focus double et visible.
- **Secondary / Ghost:** fond transparent ou papier, trait sable, texte encre.

### Chips

- **Style:** libellé compact avec point d'état, fond tonal faible et bord discret.
- **State:** texte obligatoire ; aucune signification ne dépend seulement de la couleur.

### Cards / Containers

- **Corner Style:** `10px` au maximum.
- **Background:** surface claire ou papier chaud.
- **Shadow Strategy:** aucune au repos.
- **Border:** `1px` trait sable.
- **Internal Padding:** `16px` à `24px`.

### Inputs / Fields

- **Style:** fond clair, contour sable, rayon `6px`, hauteur minimale `44px`.
- **Focus:** contour cuivre et anneau externe translucide.
- **Error / Disabled:** message textuel adjacent ; contraste maintenu.

### Navigation

Rail latéral stable sur grand écran, barre compacte sur mobile. L'élément actif utilise un fond cuivre très pâle, une encre sombre et un repère de 2 px.

### Basket Ledger

Liste structurée des articles au centre, quantités modifiables à la caisse et total fixe dans une zone récapitulative. Les événements techniques ne concurrencent jamais les lignes du panier.

## 6. Do's and Don'ts

### Do:

- **Do** placer articles, quantités, prix et total avant les informations du matériel.
- **Do** utiliser des séparateurs de `1px` et l'échelle d'espacement `8 / 16 / 24 / 32`.
- **Do** afficher des états vides qui indiquent la prochaine action concrète.
- **Do** respecter une cible tactile de `44px` et un focus visible.

### Don't:

- **Don't** afficher ou demander un code-barres.
- **Don't** construire un tableau de bord rempli de graphiques, métriques fictives ou cartes décoratives.
- **Don't** utiliser un style futuriste sombre, néon, verre dépoli ou gradient violet de démonstration IA.
- **Don't** ajouter une animation gratuite, du jargon technique au caissier ou une navigation expérimentale.
- **Don't** utiliser des emojis comme icônes.
