# Enrôlement RFID et paiement wallet

Django est la source de vérité. La Raspberry lit l’UID et envoie des labels ; elle ne crée pas un client, ne calcule pas le total, ne modifie pas le wallet et ne décide pas seule qu’une vente est payée.

## Cycle d’une carte

1. Le premier scan d’une carte connue crée une nouvelle facture `OPEN` pour cette Raspberry et identifie le client.
2. Les détections suivantes sont rattachées automatiquement à cette facture active grâce au `device_id`.
3. Le second passage de la même carte demande un paiement RFID. Django vérifie le client, le solde et le stock dans une transaction, débite le wallet, crée la vente, diminue le stock et clôture la facture.
4. Un caissier peut aussi vérifier la facture puis confirmer un paiement manuel. Toute facture clôturée apparaît dans **Factures**.
5. Après acquittement de la réinitialisation par la Pi, le prochain scan RFID crée une nouvelle facture.

Une seule facture peut être `OPEN` ou `CHECKOUT_PENDING` par Raspberry. Le système conserve sans limite fonctionnelle les factures terminées dans l’historique.

## Carte inconnue

Une carte inconnue crée une unique `RfidEnrollmentRequest` et renvoie HTTP `202 RFID_ENROLLMENT_PENDING`. Aucun achat n’est ouvert. Un administrateur l’associe à un client existant ou crée le client et son wallet, puis le client retire et représente la carte.

Une demande refusée ne réapparaît pas à chaque lecture. Une carte ou un client désactivé ne peut ni démarrer ni payer un achat.

## Installation

Sur le backend :

```powershell
cd "C:\dev\kitunga nehemie\backend"
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py provision_device KITUNGA-PI-001 101
.\start_lan_server.ps1
```

Sur la Pi :

```ini
API_MODE=real
API_BASE_URL=http://IP_DU_PC:8000
DEVICE_ID=KITUNGA-PI-001
RFID_MODE=hardware
```

Il n’existe ni `DEVICE_SECRET`, ni QR code, ni procédure d’appairage. Le `DEVICE_ID` doit correspondre à un appareil existant et activé dans Django.

## Dépannage

- `401 DEVICE_UNAUTHORIZED` : vérifier `DEVICE_ID` et le statut activé de la Raspberry dans Django.
- `404 API_ROUTE_NOT_FOUND` : relancer le backend à jour et vérifier `API_BASE_URL`.
- `409 DEVICE_RESET_PENDING` : la Pi doit acquitter la commande du paiement précédent.
- `409 NO_ACTIVE_INVOICE` : présenter d’abord une carte RFID connue.

Pour vérifier le réseau :

```bash
curl http://IP_DU_PC:8000/health/live
```

Les notifications d’enrôlement restent réservées aux superutilisateurs et membres du groupe `Administrateur`. L’UID complet n’est affiché que sur la page protégée **Cartes RFID**.
