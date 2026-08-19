# API backend Kitunga

Django reste la source de vérité des factures, prix, wallets, paiements, ventes et stocks. La Raspberry est identifiée uniquement par son `device_id`, présent dans l’URL. Elle ne configure aucun secret et ne manipule aucun identifiant de panier ou de facture.

## Mise en route

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py provision_device KITUNGA-PI-01 101
.\.venv\Scripts\python.exe manage.py provision_terminal CAISSE-01
.\.venv\Scripts\daphne.exe -b 0.0.0.0 -p 8000 core.asgi:application
```

`provision_device` enregistre seulement le `device_id` et le numéro de matrice. Le terminal de caisse conserve son authentification `Terminal <terminal_code>:<secret>`.

## Contrat Raspberry courant

| Méthode | Chemin | Rôle |
|---|---|---|
| `POST` | `/api/iot/devices/{device_id}/invoice/start/` | Identifie la carte et crée ou reprend la facture active |
| `POST` | `/api/iot/devices/{device_id}/invoice/detections/` | Ajoute une détection YOLO à la facture active |
| `GET` | `/api/iot/devices/{device_id}/invoice/status/` | Retourne `IDLE`, `ACTIVE`, `CHECKOUT_PENDING` ou `PAID` |
| `POST` | `/api/iot/devices/{device_id}/invoice/rfid-payment/` | Débite le wallet et clôture la facture |
| `POST` | `/api/v1/devices/{device_id}/heartbeat` | Met à jour la présence de la Pi sans créer de facture |
| `POST` | `/api/v1/devices/{device_id}/commands/{command_id}/ack` | Acquitte la réinitialisation après paiement |

Une détection ou un paiement porte `Idempotency-Key: <UUID>`. Le retry d’une même opération ne peut pas ajouter deux fois un article, débiter deux fois le wallet ou décrémenter deux fois le stock.

### Démarrer une facture

```http
POST /api/iot/devices/KITUNGA-PI-01/invoice/start/
Content-Type: application/json

{"rfid_uid":"04A732B19C"}
```

```json
{
  "status": "ACTIVE",
  "customer": {"id": "CUST-0042", "display_name": "Monsieur X"}
}
```

Le heartbeat ne crée jamais de facture. Seule cette première lecture d’une carte connue le fait. Une carte inconnue renvoie HTTP `202` avec `RFID_ENROLLMENT_PENDING`, sans facture.

### Ajouter une détection

```http
POST /api/iot/devices/KITUNGA-PI-01/invoice/detections/
Idempotency-Key: 0d614e55-53b5-4ccb-b54f-df9c5e83f107
Content-Type: application/json

{"label":"ESP32","confidence":0.95}
```

Le backend retrouve la facture `OPEN` de la Pi. Aucun `basket_id` n’est accepté ni renvoyé au client courant.

### Confirmer le paiement RFID

```http
POST /api/iot/devices/KITUNGA-PI-01/invoice/rfid-payment/
Idempotency-Key: 94972e7d-3da1-430b-a2af-810dd89157b4
Content-Type: application/json

{"rfid_uid":"04A732B19C"}
```

```json
{
  "status": "PAID",
  "payment_status": "PAID",
  "sale_number": "KIT-20260819-ABCDEF1234",
  "reset_command_id": "86f47bc2-5948-40f7-948d-44fd0c12a011"
}
```

Dans une transaction unique, Django vérifie la carte et le client, recalcule le total, vérifie le solde et le stock, débite le wallet, crée la vente et ses lignes, diminue le stock et clôture la facture.

## API V1 complémentaire

Les routes V1 historiques de heartbeat, événements détaillés, caisse et diagnostic restent disponibles. Une détection V1 sans facture active est refusée ; elle ne crée plus de session automatiquement. Les routes de caisse restent protégées par une session Django, et le scanner optionnel par son secret terminal.

## Erreurs utiles

- `401 DEVICE_UNAUTHORIZED` : le `device_id` n’existe pas ou la Raspberry est désactivée dans Django.
- `409 NO_ACTIVE_INVOICE` : aucune première lecture RFID valide n’a ouvert de facture.
- `402 INSUFFICIENT_FUNDS` : le wallet ne couvre pas le total ; wallet, stock et facture restent inchangés.
- `403 RFID_MISMATCH` : la carte de paiement n’appartient pas au client de la facture.
- `409 CHECKOUT_REQUIRED` : la facture a changé d’état pendant l’opération.

Les ventes clôturées sont consultables dans **Factures** avec leurs lignes, le client, le moyen de paiement, l’appareil et l’opérateur éventuel.
