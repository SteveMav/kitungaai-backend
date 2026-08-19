# Guide Raspberry Pi — cycle de facturation RFID

Ce guide décrit le flux courant. La Raspberry Pi est identifiée uniquement par
son `DEVICE_ID` sur le réseau local sécurisé. Elle ne possède ni secret, ni QR
d'appairage et ne conserve aucun identifiant de panier ou de facture.

## Principe

1. La première lecture d'une carte RFID connue ouvre une facture sur le backend.
2. Les détections de la caméra sont rattachées à la facture active de la Pi.
3. Une seconde lecture de la même carte demande le paiement RFID.
4. Django vérifie le client, le wallet et le stock, puis débite le wallet,
   décrémente le stock et clôture la facture dans une seule transaction.
5. La Pi exécute la commande de réinitialisation et l'acquitte.
6. La prochaine lecture RFID ouvre une nouvelle facture.

Le paiement peut aussi être confirmé manuellement par un caissier. Les factures
clôturées restent consultables dans **Factures**.

## 1. Enregistrer la Pi dans Django

Depuis le dossier `backend` :

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py provision_device KITUNGA-PI-001 101
```

La commande enregistre seulement le `device_id` et le numéro de matrice. Elle ne
génère aucun secret.

## 2. Configurer le client Raspberry

Dans le fichier `.env` local du client :

```ini
API_MODE=real
API_BASE_URL=http://IP_DU_PC:8000
DEVICE_ID=KITUNGA-PI-001
RFID_MODE=hardware
HARDWARE_ENABLED=true
MATRIX_ENABLED=true
PREVIEW_ENABLED=true
```

`DEVICE_ID` doit correspondre exactement à un appareil existant et activé dans
Django. Ne configurez pas de `DEVICE_SECRET`, de `BASKET_ID` ou de
`SESSION_ID` : ces valeurs ne font pas partie du contrat du client.

Vérifier le réseau avant de démarrer :

```bash
curl http://IP_DU_PC:8000/health/live
```

## 3. Contrat utilisé par la Pi

| Méthode | Chemin | Effet |
|---|---|---|
| `POST` | `/api/iot/devices/{device_id}/invoice/start/` | Ouvre ou reprend la facture après lecture RFID |
| `POST` | `/api/iot/devices/{device_id}/invoice/detections/` | Ajoute un article à la facture active |
| `GET` | `/api/iot/devices/{device_id}/invoice/status/` | Lit l'état courant ou la commande de reset |
| `POST` | `/api/iot/devices/{device_id}/invoice/rfid-payment/` | Demande au backend de confirmer et exécuter le paiement |
| `POST` | `/api/v1/devices/{device_id}/heartbeat` | Signale la présence sans créer de facture |
| `POST` | `/api/v1/devices/{device_id}/commands/{command_id}/ack` | Confirme que le reset local est terminé |

### Première lecture RFID

```http
POST /api/iot/devices/KITUNGA-PI-001/invoice/start/
Content-Type: application/json

{"rfid_uid":"04A732B19C"}
```

Une carte connue retourne `ACTIVE` avec le client. Une carte inconnue retourne
`202 RFID_ENROLLMENT_PENDING` sans créer de facture. Le heartbeat, le démarrage
du programme et la première détection ne créent jamais de facture.

### Détection d'un article

```http
POST /api/iot/devices/KITUNGA-PI-001/invoice/detections/
Idempotency-Key: 0d614e55-53b5-4ccb-b54f-df9c5e83f107
Content-Type: application/json

{"label":"ESP32","confidence":0.95}
```

Le backend retrouve la facture active grâce au `device_id`. Le client réutilise
la même clé d'idempotence lors d'un retry réseau.

### Paiement RFID

```http
POST /api/iot/devices/KITUNGA-PI-001/invoice/rfid-payment/
Idempotency-Key: 94972e7d-3da1-430b-a2af-810dd89157b4
Content-Type: application/json

{"rfid_uid":"04A732B19C"}
```

La réponse `PAID` contient le numéro public de la facture et l'identifiant de la
commande de reset. La Pi n'a pas à interpréter un identifiant interne de panier.

## 4. États attendus côté Pi

- `IDLE` : aucune facture active ; attendre une première carte RFID.
- `ACTIVE` : client identifié ; accepter les détections.
- `CHECKOUT_PENDING` : facture verrouillée ; ne plus modifier les lignes.
- `PAID` : paiement confirmé par Django ; vider le tracking local et acquitter
  la commande de reset.

Une seule facture peut être active par Pi afin que chaque détection ait une
destination non ambiguë. Le backend conserve autant de factures terminées que
nécessaire dans l'historique.

## 5. Règles de fiabilité

- Générer une clé UUID par détection logique et par tentative de paiement.
- Réutiliser cette même clé pendant les retries réseau.
- Ne jamais débiter un wallet, calculer le total ou modifier le stock côté Pi.
- Suspendre les détections tant qu'aucune carte connue n'a ouvert de facture.
- Après `PAID`, vider le tracking avant d'acquitter `RESET_SESSION`.
- Une erreur réseau n'est pas une confirmation de paiement : relire le statut.

## 6. Erreurs courantes

- `401 DEVICE_UNAUTHORIZED` : `DEVICE_ID` inconnu ou appareil désactivé.
- `409 NO_ACTIVE_INVOICE` : présenter d'abord une carte RFID connue.
- `409 DEVICE_RESET_PENDING` : terminer et acquitter le reset précédent.
- `403 RFID_MISMATCH` : la carte ne correspond pas au client de la facture.
- `402 INSUFFICIENT_FUNDS` : solde insuffisant ; aucune donnée financière ou de
  stock n'a été modifiée.
- `422 UNCATALOGUED_OBJECT` : label caméra sans produit associé.

## 7. Scanner ESP32 optionnel

L'ancien scanner de matrice reste un chemin de caisse optionnel. Son terminal
conserve une authentification séparée `Terminal <terminal_code>:<secret>`. Cela
ne concerne pas l'identité de la Raspberry Pi et n'est pas requis pour le flux
RFID ou la confirmation manuelle.

## 8. Validation sur site

- [ ] La Pi atteint `/health/live`.
- [ ] Un `DEVICE_ID` inconnu est refusé et un appareil activé est accepté sans secret.
- [ ] Le heartbeat seul ne crée aucune facture.
- [ ] Une première carte connue ouvre une facture avec le bon client.
- [ ] Une détection apparaît dans la facture active.
- [ ] La même clé d'idempotence ne double pas la quantité.
- [ ] Une autre carte ne peut pas payer la facture.
- [ ] Un solde insuffisant ne modifie ni wallet, ni stock, ni facture.
- [ ] Le paiement RFID ou manuel crée une seule vente et décrémente le stock une fois.
- [ ] La facture terminée est visible dans **Factures**.
- [ ] Après reset, la prochaine carte ouvre une nouvelle facture.
