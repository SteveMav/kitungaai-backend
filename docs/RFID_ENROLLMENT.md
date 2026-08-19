# Enrôlement RFID et paiement wallet

Ce guide décrit le cycle réel d'une carte RFID Kitunga. Django reste la source de vérité : la Raspberry Pi lit une carte et envoie des labels de produits, mais elle ne crée jamais un client, ne modifie jamais un solde et ne décide jamais d'une vente.

## Cycle d'une carte

1. Le client pose sa carte sur le lecteur de la Pi.
2. Si l'UID est déjà lié à une carte RFID active et à un client actif, Django ouvre le panier et la Pi passe à l'état `ACTIVE`.
3. Si l'UID est inconnu, Django crée une unique `RfidEnrollmentRequest` et répond `202 RFID_ENROLLMENT_PENDING`. Aucun panier n'est ouvert, aucun produit ne peut être ajouté et aucun paiement n'est possible.
4. Tout administrateur connecté voit une notification sur n'importe quelle page de l'interface, puis ouvre **Cartes RFID**.
5. L'administrateur associe la carte à un client existant ou crée un client. Dans le second cas, le portefeuille est créé à zéro automatiquement.
6. Le client retire puis présente à nouveau sa carte. Django reconnaît alors la carte et ouvre le panier. Cette seconde lecture évite de démarrer un achat après le départ de la personne.
7. Après validation du panier à la caisse, la même carte règle l'achat. Django vérifie le client, le solde et le stock dans une même transaction avant de débiter le wallet et créer la vente.

Une demande refusée reste refusée : elle ne réapparaît pas à chaque lecture. Une carte désactivée n'est pas proposée à l'enrôlement et ne peut pas ouvrir de panier.

## Première installation

Sur le PC qui héberge Django :

```powershell
cd "C:\dev\kitunga nehemie\backend"
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\start_lan_server.ps1
```

Le compte doit être superutilisateur ou membre du groupe `Administrateur`. Ce groupe reçoit automatiquement les droits sur les clients, portefeuilles, cartes et demandes RFID après la migration.

Sur la Pi, copier la version complète et récente de `kitunga_pi_client/`, puis créer le fichier privé `.env` :

```bash
cd /home/admin/mon_oled/kitunga_pi_client
cp .env.example .env
nano .env
chmod 600 .env
```

```ini
API_MODE=real
API_BASE_URL=http://IP_DU_PC:8000
DEVICE_ID=KITUNGA-PI-001
DEVICE_SECRET=secret_affiche_par_provision_device
RFID_MODE=hardware
```

Le code d'appareil et le secret sont créés une seule fois :

```powershell
.\.venv\Scripts\python.exe manage.py provision_device KITUNGA-PI-001 101
```

Ne lancez `provision_device --rotate` que pour remplacer volontairement le secret. Après une rotation, remplacez immédiatement `DEVICE_SECRET` dans `.env` sur la Pi et relancez le client.

## Notifications et droits

- Le canal WebSocket `/ws/v1/rfid-enrollments/` diffuse seulement le numéro de demande, la matrice source et le nombre de demandes en attente. L'UID complet n'est visible que sur la page protégée **Cartes RFID**.
- Seuls les superutilisateurs et les membres du groupe `Administrateur` peuvent ouvrir la page, accepter/refuser une demande ou se connecter à ce canal.
- Les caissiers et superviseurs ne reçoivent pas les notifications RFID ni l'UID de la carte.

## Dépannage Pi : 401 et 404

### `DEVICE_SECRET_MISSING`

Le fichier `.env` ne contient pas `DEVICE_SECRET`. Le client n'envoie aucune requête dans ce cas. Ajoutez le secret puis relancez `python main.py`.

### `401 DEVICE_UNAUTHORIZED`

Le Pi a atteint Django, mais le couple `DEVICE_ID`/`DEVICE_SECRET` est faux, le secret a été tourné, ou l'appareil est désactivé dans Django. Vérifiez que le code est identique des deux côtés et que la ligne du secret ne contient pas d'espace ajouté.

### `404 API_ROUTE_NOT_FOUND`

L'adresse du backend est atteignable mais le processus Django lancé ne contient pas les nouvelles routes, ou `API_BASE_URL` vise le mauvais serveur. Sur le PC, arrêtez l'ancien processus avec `Ctrl+C`, puis relancez :

```powershell
.\start_lan_server.ps1
```

Sur la Pi, vérifiez l'URL avec :

```bash
curl http://IP_DU_PC:8000/health/live
```

Utilisez l'IPv4 du PC, jamais celle de la Pi. Si le PC reçoit une nouvelle adresse DHCP, modifiez uniquement `API_BASE_URL` dans `.env` jusqu'à ce qu'une réservation DHCP soit configurée sur le routeur.
