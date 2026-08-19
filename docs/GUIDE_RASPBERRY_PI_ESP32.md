# Guide terrain — Raspberry Pi et scanner ESP32

Ce guide décrit ce qu'il faut faire devant le matériel pour connecter le code déjà installé à l'API Kitunga V1.

> Important : le dépôt actuel contient le backend Django, mais pas le code source de la Raspberry Pi ni le firmware `.ino`/`.cpp` de l'ESP32. Les contrats API ci-dessous correspondent au backend réellement implémenté et testé. Le code matériel devra être comparé à ces contrats sur place.

## 1. Comprendre le rôle de chaque élément

- La **Raspberry Pi du panier** observe la caméra, stabilise les détections et envoie seulement des événements métier `ITEM_ADDED` ou `ITEM_REMOVED`.
- La **matrice 8×8 du panier** affiche le `matrix_id` stable du panier physique, compris entre `1` et `4095`.
- Le **scanner ESP32 de la caisse** lit cette matrice et envoie le `matrix_id` à Django.
- **Django** possède les produits, les prix, le contenu du panier, les ventes et le stock.
- Le **caissier** garde la décision finale. Un scan sélectionne un panier, mais ne confirme jamais une vente.

Il n'existe aucun code-barres dans ce flux.

## 2. Avant d'aller devant la Raspberry Pi

### 2.1 Trouver l'adresse IP du serveur Django

Sur l'ordinateur Windows qui exécute Django :

```powershell
ipconfig
```

Relever l'adresse IPv4 du réseau local, par exemple `192.168.1.20`. Dans la suite du guide :

```text
SERVER_IP=192.168.1.20
API_BASE=http://192.168.1.20:8000/api/v1
```

La Raspberry Pi, l'ESP32 et le serveur doivent être sur le même réseau local.

### 2.2 Provisionner le panier

Dans le dossier `backend`, avec l'environnement virtuel activé :

```powershell
python manage.py provision_device KITUNGA-PI-01 101
```

La commande affiche trois valeurs :

```text
device_code=KITUNGA-PI-01
matrix_id=101
secret=...
```

Noter le secret immédiatement dans un emplacement privé. Il n'est affiché qu'une fois et ne doit pas être placé dans Git ou imprimé dans les logs.

Si l'appareil existe déjà et que son secret est perdu :

```powershell
python manage.py provision_device KITUNGA-PI-01 101 --rotate
```

La rotation invalide immédiatement l'ancien secret.

### 2.3 Associer les labels de la caméra aux produits

Dans l'interface Kitunga :

1. Ouvrir **Stock**.
2. Ouvrir le produit.
3. Renseigner **Labels reconnus par la caméra**.
4. Utiliser exactement le texte produit par le modèle, par exemple `Arduino-Mega`.

Un label inconnu du catalogue est conservé dans le panier comme **objet non
répertorié**. Il reste sans prix et doit être traité par le caissier avant la
vente.

### 2.4 Lancer Django sur le réseau local

```powershell
$env:DJANGO_ALLOWED_HOSTS="localhost,127.0.0.1,192.168.1.20"
daphne -b 0.0.0.0 -p 8000 core.asgi:application
```

Remplacer `192.168.1.20` par l'adresse réelle du serveur. Si Windows demande une autorisation pare-feu, autoriser le port `8000` uniquement sur le réseau privé.

Vérifier depuis l'ordinateur :

```powershell
Invoke-WebRequest http://192.168.1.20:8000/health/live
```

Réponse attendue :

```json
{"status":"ok"}
```

## 3. Devant la Raspberry Pi : procédure étape par étape

### Étape 1 — Sauvegarder le code existant

Avant toute modification, copier le dossier du programme ou créer un commit Git local. Ne pas écraser le programme qui pilote déjà la caméra et la matrice.

### Étape 2 — Vérifier l'heure et le réseau

```bash
timedatectl status
sudo timedatectl set-ntp true
ping -c 3 192.168.1.20
curl -i http://192.168.1.20:8000/health/live
```

Ne pas continuer tant que le `curl` ne renvoie pas `HTTP/1.1 200 OK`.

### Étape 3 — Configurer l'identité de la Pi

Le programme de la Pi doit recevoir ces valeurs par variables d'environnement ou par un fichier local non versionné :

```text
KITUNGA_API_BASE=http://192.168.1.20:8000/api/v1
KITUNGA_DEVICE_CODE=KITUNGA-PI-01
KITUNGA_DEVICE_SECRET=SECRET_AFFICHE_PAR_PROVISION_DEVICE
KITUNGA_MATRIX_ID=101
```

Le `matrix_id` configuré doit être exactement le motif affiché par la matrice 8×8.

Exemple de fichier système protégé :

```bash
sudo install -d -m 700 /etc/kitunga
sudo nano /etc/kitunga/edge.env
sudo chmod 600 /etc/kitunga/edge.env
```

Ne jamais afficher `KITUNGA_DEVICE_SECRET` dans les logs.

Avant de modifier le client API existant, repérer ses appels réseau :

```bash
grep -RniE "requests\.(post|get)|http://|https://|add-detection|barcode|detected_label" .
```

Comparer ce que vous trouvez :

| Si le code actuel fait ceci | Modification nécessaire |
|---|---|
| Appelle `/api/add-detection/` ou une URL `/api/baskets/...` | Passer aux endpoints `/api/v1/devices/{device_code}/...` |
| Envoie un champ `barcode` | Le supprimer ; envoyer `detected_label` |
| N'envoie aucun heartbeat | Ajouter le heartbeat et conserver son `session.id` |
| N'envoie aucun header d'authentification | Ajouter `Authorization: Device <secret>` |
| N'a pas d'UUID persistant | Créer `event_id` et le réutiliser pendant les retries |
| Envoie une classe à chaque image | Ajouter la stabilisation et le suivi ajout/retrait |

### Étape 4 — Tester le heartbeat manuellement

```bash
API_BASE="http://192.168.1.20:8000/api/v1"
DEVICE_CODE="KITUNGA-PI-01"
DEVICE_SECRET="COLLER_LE_SECRET_ICI"

curl -i -X POST \
  "$API_BASE/devices/$DEVICE_CODE/heartbeat" \
  -H "Authorization: Device $DEVICE_SECRET" \
  -H "Content-Type: application/json" \
  -d '{
    "firmware_version": "rpi-edge-1.0.0",
    "boot_id": "TEST-BOOT-001",
    "queue_depth": 0,
    "edge_state": "READY"
  }'
```

Réponse attendue :

```json
{
  "device_code": "KITUNGA-PI-01",
  "matrix_id": 101,
  "enabled": true,
  "last_seen_at": "2026-08-14T08:15:00Z",
  "reset_state": "READY",
  "session": {
    "id": "b4da2d0b-0e71-43f4-973d-1685ee66b31b",
    "status": "OPEN",
    "version": 1
  },
  "command": null
}
```

Conserver `session.id`. Chaque événement de cette course du panier doit envoyer ce même UUID.

Si la réponse vaut `401`, le `device_code` ou le secret est incorrect. Si le réseau fonctionne, ne pas contourner cette erreur : corriger la configuration.

### Étape 5 — Adapter le cycle de démarrage du programme existant

À chaque démarrage du programme :

1. Générer un `boot_id` unique pour ce démarrage.
2. Initialiser `sequence` à `1` et l'incrémenter pour chaque événement logique.
3. Envoyer immédiatement un heartbeat.
4. Mémoriser le `session.id` reçu.
5. Afficher le `matrix_id` retourné par le serveur et vérifier qu'il correspond à la configuration locale.
6. Commencer la détection seulement lorsqu'une session `OPEN` existe et qu'aucun reset n'est en attente.

Le heartbeat peut être envoyé toutes les 15 à 30 secondes. Il sert à indiquer que la Pi est en ligne et à récupérer les commandes de réinitialisation.

### Étape 6 — Ne pas envoyer une détection à chaque image

Le programme doit transformer la vidéo en événements stables :

- plusieurs images consécutives confirment le même objet ;
- un objet déjà compté n'est pas ajouté une seconde fois tant qu'il reste dans le panier ;
- un changement de quantité produit uniquement le delta ;
- un retrait doit être confirmé avant d'envoyer `ITEM_REMOVED` ;
- chaque ajout ou retrait logique reçoit un nouvel `event_id` UUID.

Exemple incorrect : envoyer `ITEM_ADDED` 20 fois parce que l'objet est visible pendant 20 images.

Exemple correct : l'objet devient stable et absent de l'état local, donc envoyer une seule fois `ITEM_ADDED`.

### Étape 7 — Tester un ajout manuellement

Remplacer `SESSION_UUID` par le `session.id` obtenu au heartbeat. Générer un UUID avec Python, déjà présent sur la Pi.

```bash
EVENT_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
SESSION_ID="SESSION_UUID"

curl -i -X POST \
  "$API_BASE/devices/$DEVICE_CODE/events" \
  -H "Authorization: Device $DEVICE_SECRET" \
  -H "Idempotency-Key: $EVENT_ID" \
  -H "Content-Type: application/json" \
  -d "{
    \"event_id\": \"$EVENT_ID\",
    \"session_id\": \"$SESSION_ID\",
    \"boot_id\": \"TEST-BOOT-001\",
    \"sequence\": 1,
    \"captured_at\": \"$(date --iso-8601=seconds)\",
    \"action\": \"ITEM_ADDED\",
    \"detected_label\": \"arduino_mega_2560\",
    \"confidence\": \"0.9600\",
    \"quantity\": 1,
    \"model_version\": \"kitunga-model-1\"
  }"
```

Réponse correcte pour un nouvel événement :

```json
{
  "event_id": "...",
  "duplicate": false,
  "result": "applied",
  "session_id": "...",
  "version": 2,
  "line_quantity": 1
}
```

Le statut HTTP doit être `201` et `result` doit être `applied`. Ouvrir ensuite **Paniers** dans Kitunga : l'article doit apparaître.

### Étape 8 — Tester l'idempotence

Renvoyer exactement la même requête avec le même `event_id` et la même en-tête `Idempotency-Key`.

Résultat attendu :

- HTTP `200` ;
- `duplicate: true` ;
- la quantité du panier ne change pas une seconde fois.

Attention : un doublon d'un événement précédemment refusé peut également revenir en HTTP `200`. Le programme doit vérifier `result == "applied"`, et pas seulement le code HTTP.

### Étape 9 — Tester un retrait

Envoyer le même format avec un nouvel UUID et :

```json
{
  "action": "ITEM_REMOVED",
  "quantity": 1
}
```

Un retrait supérieur à la quantité connue est refusé avec `result: "invalid_removal"`.

### Étape 10 — Ajouter une file locale persistante

La Pi doit conserver les événements non livrés dans une petite base SQLite locale. Pour chaque événement, conserver au minimum :

- `event_id` ;
- `session_id` ;
- le JSON complet ;
- la date de création ;
- le nombre de tentatives ;
- le dernier résultat.

Règles de réessai :

- timeout, coupure réseau ou HTTP `5xx` : réessayer le même événement et le même UUID avec délai progressif ;
- HTTP `429` : attendre puis réessayer le même événement ;
- HTTP `401` : arrêter l'envoi et signaler une erreur de configuration ;
- HTTP `422` : isoler l'événement, corriger le payload et ne pas boucler sans fin ;
- `uncatalogued_object` : afficher l'objet non répertorié et le faire vérifier à la caisse ;
- `basket_locked` : arrêter les détections pour cette session et continuer les heartbeats.

Ne jamais créer un nouvel UUID lors d'un simple réessai réseau.

### Étape 11 — Traiter la commande de réinitialisation

Après la confirmation d'une vente, le heartbeat renvoie :

```json
{
  "command": {
    "id": "44a28a95-5fd5-4ab1-9247-4e6e18a650fd",
    "type": "RESET_SESSION",
    "session_id": "ancienne-session-uuid",
    "status": "PENDING"
  }
}
```

La Pi doit alors, dans cet ordre :

1. arrêter temporairement la détection ;
2. vider l'état de tracking et les objets actuellement comptés ;
3. archiver les événements non envoyés de l'ancienne session, sans les rattacher à une nouvelle session ;
4. remettre son état local à vide ;
5. accuser réception de la commande ;
6. refaire un heartbeat pour obtenir une nouvelle session.

ACK de commande :

```bash
COMMAND_ID="44a28a95-5fd5-4ab1-9247-4e6e18a650fd"

curl -i -X POST \
  "$API_BASE/devices/$DEVICE_CODE/commands/$COMMAND_ID/ack" \
  -H "Authorization: Device $DEVICE_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"boot_id":"TEST-BOOT-001"}'
```

Réponse attendue :

```json
{
  "command_id": "44a28a95-5fd5-4ab1-9247-4e6e18a650fd",
  "status": "ACKNOWLEDGED",
  "duplicate": false,
  "reset_state": "READY"
}
```

L'ACK est lui-même répétable. Ne jamais l'envoyer avant d'avoir réellement vidé l'état local.

## 4. Contrat API complet de la Raspberry Pi

Toutes les URLs V1 sont sans slash final.

### Authentification

```http
Authorization: Device <secret individuel de la Pi>
Content-Type: application/json
```

Le `device_code` est également présent dans l'URL.

### `POST /api/v1/devices/{device_code}/heartbeat`

| Champ | Requis | Contraintes |
|---|---:|---|
| `firmware_version` | Non | Texte, 64 caractères maximum |
| `boot_id` | Non | Texte, 96 caractères maximum |
| `queue_depth` | Non | Entier `0..100000` |
| `edge_state` | Non | `READY`, `TRACKING`, `DEGRADED` ou `RESETTING` |

Réponse HTTP normale : `200`.

### `GET /api/v1/devices/{device_code}/state`

Retourne la session et la commande courantes. Utile pour le diagnostic, mais ne remplace pas le heartbeat périodique.

### `POST /api/v1/devices/{device_code}/events`

En-tête supplémentaire obligatoire :

```http
Idempotency-Key: <même UUID que event_id>
```

| Champ | Requis | Contraintes |
|---|---:|---|
| `event_id` | Oui | UUID unique par ajout/retrait logique |
| `session_id` | Oui en V1 | UUID reçu au heartbeat |
| `boot_id` | Oui | 96 caractères maximum |
| `sequence` | Oui | Entier croissant positif ou nul |
| `captured_at` | Oui | Date ISO 8601 avec fuseau horaire |
| `action` | Oui | `ITEM_ADDED` ou `ITEM_REMOVED` |
| `detected_label` | Oui | 1 à 128 caractères, lettres/chiffres/espace/point/tiret/soulignement |
| `confidence` | Oui | Décimal `0..1`, quatre décimales maximum |
| `quantity` | Oui | Entier `1..20` |
| `model_version` | Non | 64 caractères maximum |

Résultats possibles :

| HTTP initial | `result` | Signification |
|---:|---|---|
| `201` | `applied` | Événement appliqué au panier |
| `201` | `uncatalogued_object` | Objet détecté conservé au panier, sans prix catalogue |
| `409` | `basket_locked` | Panier à la caisse, reset en attente ou ancienne session |
| `409` | `version_conflict` | Modification concurrente ; recharger l'état |
| `422` | `invalid_removal` | Retrait impossible pour la quantité connue |
| `422` | validation | Payload ou clé d'idempotence invalide |
| `401` | authentification | Secret ou appareil incorrect/désactivé |
| `429` | limitation | Trop de requêtes |

Un replay connu retourne HTTP `200` avec `duplicate: true`. Toujours lire `result`.

### `POST /api/v1/devices/{device_code}/commands/{command_id}/ack`

Payload facultatif :

```json
{
  "boot_id": "PI1-BOOT-20260814-001",
  "acknowledged_at": "2026-08-14T08:30:00Z"
}
```

## 5. Scanner ESP32 de la caisse

### 5.1 Ce qui est déjà réalisé côté backend

Le backend possède et teste :

- une identité et un secret individuels par terminal ;
- l'endpoint `POST /api/v1/checkout/scans` ;
- une clé d'idempotence par scan ;
- la validation du `matrix_id` entre `1` et `4095` ;
- le contrôle des métriques de qualité ;
- la sélection et le verrouillage atomique du panier ;
- le refus des matrices inconnues ou des paniers sans session ouverte ;
- la protection contre un double scan ;
- la notification de l'interface de caisse.

Cela ne signifie pas que le firmware ESP32 présent sur le matériel est déjà conforme. Son code source n'est pas dans ce dépôt et doit être vérifié sur place.

### 5.2 Provisionner le terminal

Sur le serveur :

```powershell
python manage.py provision_terminal CAISSE-01
```

La commande retourne un secret individuel à installer sur l'ESP32.

Configuration attendue :

```text
KITUNGA_API_URL=http://192.168.1.20:8000/api/v1/checkout/scans
KITUNGA_TERMINAL_CODE=CAISSE-01
KITUNGA_TERMINAL_SECRET=SECRET_DU_TERMINAL
```

### 5.3 Requête du scanner

```http
POST /api/v1/checkout/scans
Authorization: Terminal CAISSE-01:<secret>
Idempotency-Key: 0ea231e9-17b1-4bb8-a46d-b46f76705f63
Content-Type: application/json
```

```json
{
  "event_id": "0ea231e9-17b1-4bb8-a46d-b46f76705f63",
  "matrix_id": 101,
  "frame_errors": 0,
  "copy_disagreements": 0,
  "cell_contrast": "0.7500",
  "scanned_at": "2026-08-14T08:20:00Z"
}
```

| Champ | Requis | Contraintes |
|---|---:|---|
| `event_id` | Oui | Nouvel UUID par scan logique |
| `matrix_id` | Oui | Entier `1..4095` |
| `frame_errors` | Oui | Entier `0..65535` |
| `copy_disagreements` | Oui | Entier `0..65535` |
| `cell_contrast` | Oui | Décimal positif |
| `scanned_at` | Non | Date ISO 8601 |

Avec la configuration backend par défaut, un scan accepté exige :

- `frame_errors == 0` ;
- `copy_disagreements == 0` ;
- `cell_contrast >= 0.10`.

Réponse correcte :

```json
{
  "event_id": "0ea231e9-17b1-4bb8-a46d-b46f76705f63",
  "duplicate": false,
  "result": "selected",
  "session_id": "b4da2d0b-0e71-43f4-973d-1685ee66b31b",
  "version": 3
}
```

Résultats possibles :

| HTTP initial | `result` | Action du firmware |
|---:|---|---|
| `200` | `selected` | Afficher succès ; le panier est visible à la caisse |
| `404` | `unknown_matrix` | Afficher matrice inconnue ; vérifier le provisionnement |
| `409` | `no_open_session` | Le panier n'a pas encore ouvert de session |
| `409` | `already_selected` | Le panier est déjà à une caisse ; ne pas rescanner en boucle |
| `409` | `version_conflict` | Réessayer avec un nouvel événement seulement après une nouvelle lecture physique |
| `422` | `quality_rejected` | Reprendre plusieurs lectures stables avant un nouvel envoi |
| `422` | validation | Corriger le JSON ou l'en-tête |
| `401` | authentification | Corriger le terminal ou son secret |
| `429` | limitation | Attendre avant de réessayer |

Comme pour la Pi, un doublon peut répondre HTTP `200` même si le premier résultat était un échec. Le firmware doit considérer le scan réussi uniquement si `result == "selected"`.

### 5.4 Modifications probables de l'ancien firmware ESP32

D'après l'architecture existante, l'ancien prototype envoyait ses scans à une petite base SQLite sur une Raspberry Pi. Pour la V1, vérifier et modifier :

1. l'URL doit pointer directement vers Django : `/api/v1/checkout/scans` ;
2. l'authentification doit utiliser `Terminal <terminal_code>:<secret>` ;
3. `Idempotency-Key` doit être identique à `event_id` ;
4. trois lectures stables ou une règle équivalente doivent précéder l'envoi ;
5. un scan en attente doit conserver le même UUID pendant les réessais réseau ;
6. la file RAM existante ne doit pas écraser silencieusement un scan ;
7. l'écran ou la LED doit distinguer succès, erreur de qualité, absence de session et panne réseau ;
8. l'ESP32 ne doit jamais appeler l'endpoint de confirmation de vente.

## 6. Checklist de validation physique

Effectuer les tests dans cet ordre :

### Réseau et identité

- [ ] La Pi atteint `/health/live`.
- [ ] Le heartbeat répond `200` avec le bon `device_code` et le bon `matrix_id`.
- [ ] Le panier apparaît en ligne dans l'interface.
- [ ] Un mauvais secret répond `401`.

### Détection

- [ ] Un objet posé produit un seul `ITEM_ADDED`.
- [ ] L'objet immobile pendant 30 secondes ne produit aucun ajout supplémentaire.
- [ ] Un second objet produit uniquement le delta attendu.
- [ ] Le retrait produit un seul `ITEM_REMOVED`.
- [ ] Une coupure réseau conserve l'événement localement.
- [ ] Après reconnexion, le même UUID est rejoué et la quantité ne double pas.
- [ ] Un label inconnu apparaît comme objet non répertorié dans le panier et reste bloqué à la caisse jusqu'à vérification.

### Caisse ESP32

- [ ] Le scanner effectue plusieurs lectures stables avant l'envoi.
- [ ] Le scan retourne `result: selected`.
- [ ] Le panier apparaît dans la page **Caisse**.
- [ ] Un second scan du même panier ne crée pas une nouvelle session.
- [ ] Un événement Pi envoyé après le verrouillage est refusé avec `basket_locked`.

### Vente et reset

- [ ] Le caissier peut corriger une quantité.
- [ ] Le stock ne change pas avant la confirmation.
- [ ] La confirmation décrémente le stock une seule fois.
- [ ] Le heartbeat suivant retourne `RESET_SESSION`.
- [ ] La Pi vide réellement son tracking avant l'ACK.
- [ ] L'ACK retourne `ACKNOWLEDGED`.
- [ ] Le heartbeat suivant reçoit un nouvel UUID de session.

## 7. Critères pour dire que le code matériel est « bien fait »

Le code Raspberry Pi est acceptable seulement s'il :

- stabilise les observations avant de créer un événement ;
- sait reconnaître un ajout et un retrait, pas seulement une classe visible ;
- persiste sa file hors ligne ;
- réessaie avec le même UUID ;
- conserve le `session_id` reçu au heartbeat ;
- arrête les mutations lorsque le panier est verrouillé ;
- exécute puis acquitte `RESET_SESSION` ;
- ne contient aucun secret dans le dépôt ou les logs.

Le firmware ESP32 est acceptable seulement s'il :

- lit le motif plusieurs fois et mesure la qualité ;
- envoie directement le scan à Django ;
- utilise son secret individuel ;
- gère les doublons et les coupures réseau ;
- affiche une erreur compréhensible ;
- ne déclenche jamais lui-même une vente.

Sans le code source matériel et sans le test physique de ces scénarios, il serait incorrect d'affirmer que les deux programmes sont validés.
