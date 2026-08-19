# Kitunga AI Backend

API et interface Django du système de panier intelligent Kitunga AI.

Backend Django local pour suivre les paniers physiques, vérifier leur contenu à la caisse et gérer un stock simple. Le projet n'utilise aucun code-barres : la caméra envoie un **label IA** et la carte RFID identifie puis peut confirmer le paiement du même panier.

## Démarrage rapide sous Windows PowerShell

Placez-vous dans le dossier du backend :

```powershell
cd "C:\dev\kitunga nehemie\backend"
```

Activez l'environnement virtuel existant :

```powershell
.\.venv\Scripts\Activate.ps1
```

Si PowerShell bloque l'activation, autorisez les scripts uniquement pour ce terminal puis recommencez :

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Le début de la ligne de commande doit ensuite afficher `(.venv)`.

Installez les dépendances et préparez la base :

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
```

### Option 1 : utiliser les données réelles

Créez un compte administrateur si vous n'en avez pas encore :

```powershell
python manage.py createsuperuser
```

Puis lancez le serveur :

```powershell
python manage.py runserver
```

Ouvrez [http://127.0.0.1:8000](http://127.0.0.1:8000).

### Option 2 : voir immédiatement un panier de démonstration

Cette commande locale crée un compte, un panier physique, une caisse et quelques lignes de panier :

```powershell
python manage.py setup_demo --username demo --password "kitunga-demo-2026"
python manage.py runserver
```

Connectez-vous avec `demo` et le mot de passe choisi. Pour placer ce panier dans la file de caisse :

```powershell
python manage.py setup_demo --username demo --password "kitunga-demo-2026" --checkout
```

Rafraîchissez ensuite la page **Caisse**.

## Ce que fait l'application

1. **Stock** : Django conserve le nom, le SKU, le prix, la quantité et les labels reconnus par la caméra.
2. **Facture active** : le premier scan RFID identifie le client et crée la facture ; la Raspberry envoie ensuite les détections sans gérer son identifiant interne.
3. **Direct** : la page Paniers recharge le contenu après chaque événement WebSocket.
4. **Confirmation manuelle** : depuis **Paniers**, le caissier verrouille un panier actif, le corrige si nécessaire, puis confirme la vente.
5. **Paiement RFID** : le client peut aussi retirer puis présenter à nouveau la même carte pendant que son panier est actif ; Django vérifie l'identité et le solde, puis finalise la vente.
6. **Historique et nouveau cycle** : la vente clôturée reste dans **Factures**, puis le scan RFID suivant démarre une nouvelle facture.

## Cartes RFID et wallets

La première lecture d'une carte inconnue ne crée pas de panier. Elle déclenche une demande dans **Cartes RFID**, visible par les administrateurs sur toutes les pages de l'interface. L'administrateur associe la carte à un client existant ou crée le client et son portefeuille ; le client présente ensuite la carte une seconde fois pour démarrer son achat.

Le détail du parcours, les droits, la configuration de la Pi et la résolution des erreurs `401`/`404` sont documentés dans [docs/RFID_ENROLLMENT.md](docs/RFID_ENROLLMENT.md).

## Commandes utiles

```powershell
# Vérifier le projet
python manage.py check

# Lancer tous les tests
python manage.py test

# Créer ou mettre à jour une Raspberry par son device_id
python manage.py provision_device KITUNGA-PI-01 101

# Créer une caisse
python manage.py provision_terminal CAISSE-01
```

Pour écouter sur le réseau local avec le serveur ASGI :

```powershell
.\start_lan_server.ps1
```

La Pi utilise par défaut `http://STEVEMAVUELA:8000`, donc l'adresse IP du PC
peut changer sans modifier le client. Vérifier depuis la Pi :

```bash
curl http://STEVEMAVUELA:8000/health/live
```

Si le réseau ne résout pas ce nom, essayer `STEVEMAVUELA.local`. Le pare-feu
Windows doit autoriser les connexions entrantes TCP sur le port `8000`.

La documentation des équipements et des endpoints se trouve dans [docs/API_V1.md](docs/API_V1.md). La décision d'architecture complète se trouve dans [docs/ARCHITECTURE_KITUNGA.md](docs/ARCHITECTURE_KITUNGA.md).

Le scanner ESP32 reste documenté uniquement pour la compatibilité dans [docs/GUIDE_RASPBERRY_PI_ESP32.md](docs/GUIDE_RASPBERRY_PI_ESP32.md) ; il n'est plus nécessaire pour confirmer un panier.
