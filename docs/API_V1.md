# API backend Kitunga V1

L'API V1 est servie sous `/api/v1`. Les URLs n'ont volontairement pas de slash final afin de simplifier les clients ESP32/Raspberry Pi. Django/SQLite reste la source autoritative des paniers, prix, ventes et stocks.

## Mise en route

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py provision_device KITUNGA-PI-01 101
.\.venv\Scripts\python.exe manage.py provision_terminal CAISSE-01
.\.venv\Scripts\daphne.exe -b 0.0.0.0 -p 8000 core.asgi:application
```

Les commandes de provisionnement affichent le secret une seule fois. Installer ce secret sur l'équipement et ne jamais l'enregistrer dans Git ou dans les logs. Les labels IA sont associés explicitement aux produits dans l'administration Django (`VisionLabel`).

Le guide d'installation et de validation devant le matériel se trouve dans [`GUIDE_RASPBERRY_PI_ESP32.md`](GUIDE_RASPBERRY_PI_ESP32.md).

## Authentification

- Raspberry Pi : `Authorization: Device <secret>` sur une URL contenant `device_code`.
- Scanner : `Authorization: Terminal <terminal_code>:<secret>`.
- Caisse : session Django avec CSRF et appartenance à `Caissier`, `Superviseur` ou `Administrateur`.
- Toute détection, tout scan et toute finalisation portent `Idempotency-Key`, identique à l'UUID de l'événement ou de l'opération.

## Endpoints

| Méthode | Chemin | Acteur |
|---|---|---|
| `POST` | `/api/v1/devices/{device_code}/heartbeat` | Raspberry Pi |
| `POST` | `/api/v1/devices/{device_code}/events` | Raspberry Pi |
| `POST` | `/api/v1/devices/{device_code}/commands/{command_id}/ack` | Raspberry Pi |
| `GET` | `/api/v1/devices/{device_code}/state` | Raspberry Pi |
| `POST` | `/api/v1/checkout/scans` | Scanner ESP32 |
| `GET` | `/api/v1/cashier/sessions/{session_id}` | Caissier |
| `PATCH` | `/api/v1/cashier/sessions/{session_id}/lines/{line_id}` | Caissier |
| `POST` | `/api/v1/cashier/sessions/{session_id}/complete` | Caissier |
| `POST` | `/api/v1/cashier/sessions/{session_id}/release` | Caissier |
| `POST` | `/api/v1/cashier/sessions/{session_id}/cancel` | Superviseur |
| `GET` | `/api/v1/dashboard/stats` | Utilisateur de caisse |

## Exemple de détection

```http
POST /api/v1/devices/KITUNGA-PI-01/events
Authorization: Device <secret>
Idempotency-Key: 0d614e55-53b5-4ccb-b54f-df9c5e83f107
Content-Type: application/json

{
  "event_id": "0d614e55-53b5-4ccb-b54f-df9c5e83f107",
  "session_id": "b4da2d0b-0e71-43f4-973d-1685ee66b31b",
  "boot_id": "PI1-20260814-001",
  "sequence": 42,
  "captured_at": "2026-08-14T01:25:10Z",
  "action": "ITEM_ADDED",
  "detected_label": "arduino_mega_2560",
  "confidence": 0.96,
  "quantity": 1,
  "model_version": "kitunga-yolo-1"
}
```

Une première livraison acceptée renvoie `201`. Le replay de la même clé renvoie `200` avec `duplicate: true`, sans modifier une seconde fois la quantité.

`session_id` vient de la réponse du heartbeat. Il empêche un événement retardé de l'ancien cycle d'altérer le panier ouvert après un reset.

## WebSockets et santé

- `/ws/v1/cashier/terminals/{terminal_code}/`
- `/ws/v1/baskets/{matrix_id}/`
- `/health/live`
- `/health/ready`

Les WebSockets exigent une session Django et un rôle de caisse. À chaque reconnexion, le navigateur recharge l'état complet par HTTP.

## Compatibilité Raspberry Pi RFID

Le client `kitunga_pi_client` utilise le contrat suivant, authentifié avec
`Authorization: Device <secret>` et `X-Device-Code` :

| Méthode | Chemin | Rôle |
|---|---|---|
| `POST` | `/api/iot/sessions/start/` | Lie une carte RFID active à la session du panier |
| `POST` | `/api/iot/baskets/{uuid}/detections/` | Ajoute une détection YOLO, avec `Idempotency-Key` |
| `GET` | `/api/iot/baskets/{uuid}/status/` | Retourne `ACTIVE`, `CHECKOUT_PENDING`, `PAID` ou `CANCELLED` |
| `POST` | `/api/iot/baskets/{uuid}/rfid-payment/` | Débite le wallet et finalise la vente, avec `Idempotency-Key` |

La recharge des wallets se fait dans l'administration Django afin de conserver
le montant, l'agent et le motif dans le journal `WalletTransaction`. Une carte
RFID n'est qu'un identifiant : le prix, le solde, le stock et la vente restent
calculés par Django.

Après un paiement RFID, la réponse fournit `reset_command_id`. La Pi acquitte
cette commande sur l'endpoint V1 existant avant d'ouvrir la session suivante.

Une carte inconnue reçoit désormais `202` avec `status: RFID_ENROLLMENT_PENDING`.
Django crée alors une demande à traiter par un administrateur dans l'interface
**Cartes RFID**, sans ouvrir de panier. Les erreurs d'authentification appareil
retournent un objet JSON `status: DEVICE_UNAUTHORIZED` avec HTTP `401`.
