# VideoGen API — Guide de déploiement VPS Ubuntu

Ce guide permet à un développeur qui ne connaît pas le projet de déployer
l'API VideoGen en production sur un VPS Ubuntu 22.04 LTS, de bout en bout,
sans intervention externe.

**Stack déployée :** Python 3.12 · FastAPI · Gunicorn + Uvicorn workers ·
systemd · nginx (reverse proxy TLS)

---

## Table des matières

1. [Prérequis](#1-prérequis)
2. [Installation étape par étape](#2-installation-étape-par-étape)
3. [Configuration nginx](#3-configuration-nginx)
4. [Variables d'environnement](#4-variables-denvironnement)
5. [Vérification du déploiement](#5-vérification-du-déploiement)
6. [Commandes utiles](#6-commandes-utiles)
7. [Mise à jour](#7-mise-à-jour)
8. [Rollback](#8-rollback)

---

## 1. Prérequis

### Serveur

| Élément       | Requis                          |
|---------------|---------------------------------|
| OS            | Ubuntu 22.04 LTS (Jammy)        |
| CPU           | 2 vCPU minimum                  |
| RAM           | 2 Go minimum                    |
| Disque        | 20 Go minimum (clips temporaires)|
| Accès réseau  | Ports 80 et 443 ouverts         |

### Logiciels à installer

```bash
sudo apt update && sudo apt upgrade -y

# Python 3.12 (disponible dans deadsnakes PPA)
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt install -y python3.12 python3.12-venv python3.12-dev

# Outils système
sudo apt install -y git nginx certbot python3-certbot-nginx curl

# Vérifier les versions
python3.12 --version   # Python 3.12.x
nginx -v               # nginx/1.x.x
git --version          # git version 2.x.x
```

### Prérequis externes (avant de commencer)

Les clés API suivantes doivent être disponibles :

- Anthropic (Claude)
- ElevenLabs
- Kling AI (access key + secret key)
- Pexels
- Creatomate
- Compte de service Google (fichier JSON téléchargé)

---

## 2. Installation étape par étape

### 2.1 Créer l'utilisateur dédié

```bash
# Créer un utilisateur système sans shell de login (sécurité)
sudo useradd --system --shell /usr/sbin/nologin --home /opt/videogen videogen

# Créer l'arborescence de travail
sudo mkdir -p /opt/videogen/{api,venv,library/clips,library}
sudo chown -R videogen:videogen /opt/videogen
```

### 2.2 Cloner le dépôt

```bash
# Cloner en tant qu'utilisateur courant (on transfèrera les droits après)
cd /opt/videogen
sudo -u videogen git clone https://github.com/tobiags/video-api-n8n.git api

# Vérifier le contenu
ls /opt/videogen/api
# Attendu : app/  gunicorn.conf.py  pyproject.toml  systemd/  ...
```

### 2.3 Créer le virtualenv et installer les dépendances

```bash
# Créer le venv au nom de l'utilisateur videogen
sudo -u videogen python3.12 -m venv /opt/videogen/venv

# Installer les dépendances depuis pyproject.toml
sudo -u videogen /opt/videogen/venv/bin/pip install --upgrade pip
sudo -u videogen /opt/videogen/venv/bin/pip install -e /opt/videogen/api

# Vérifier que gunicorn et uvicorn sont disponibles
/opt/videogen/venv/bin/gunicorn --version
/opt/videogen/venv/bin/uvicorn --version
```

### 2.4 Déposer le compte de service Google

```bash
# Copier le JSON téléchargé depuis Google Cloud Console
sudo cp /chemin/vers/service_account.json /opt/videogen/service_account.json
sudo chown videogen:videogen /opt/videogen/service_account.json
sudo chmod 600 /opt/videogen/service_account.json   # lecture seule pour le propriétaire
```

### 2.5 Configurer le fichier `.env`

```bash
# Copier l'exemple fourni dans le dépôt
sudo -u videogen cp /opt/videogen/api/.env.example /opt/videogen/api/.env

# Éditer avec les vraies valeurs (voir section 4 pour le détail)
sudo nano /opt/videogen/api/.env

# Sécuriser : seul videogen peut lire le fichier
sudo chmod 600 /opt/videogen/api/.env
sudo chown videogen:videogen /opt/videogen/api/.env
```

Valeurs minimales à renseigner dans `.env` pour un premier démarrage :

```ini
ENVIRONMENT=production
API_SECRET_KEY=<VOTRE_TOKEN_SECRET>     # python -c "import secrets; print(secrets.token_hex(32))"
ANTHROPIC_API_KEY=<CLE_ANTHROPIC>
ELEVENLABS_API_KEY=<CLE_ELEVENLABS>
ELEVENLABS_DEFAULT_VOICE_ID=<ID_CLONE_VOCAL>
KLING_ACCESS_KEY=<CLE_KLING>
KLING_SECRET_KEY=<SECRET_KLING>
PEXELS_API_KEY=<CLE_PEXELS>
CREATOMATE_API_KEY=<CLE_CREATOMATE>
CREATOMATE_TEMPLATE_VERTICAL=<ID_TEMPLATE_9_16>
CREATOMATE_TEMPLATE_HORIZONTAL=<ID_TEMPLATE_16_9>
GOOGLE_SERVICE_ACCOUNT_PATH=/opt/videogen/service_account.json
GOOGLE_DRIVE_FOLDER_ID=<ID_DOSSIER_DRIVE>
GOOGLE_SHEETS_ID=<ID_GOOGLE_SHEETS>
N8N_WEBHOOK_NOTIFICATION_URL=http://localhost:5678/webhook/videogen-callback
```

> **Note WORKERS :** garder `WORKERS=1` jusqu'à l'intégration Redis (Jour 2).
> Le job store est en mémoire et ne peut pas être partagé entre workers.

### 2.6 Installer et activer le service systemd

```bash
# Copier le fichier service fourni dans le dépôt
sudo cp /opt/videogen/api/systemd/videogen.service /etc/systemd/system/videogen.service

# Recharger systemd pour qu'il découvre le nouveau service
sudo systemctl daemon-reload

# Activer le démarrage automatique au boot
sudo systemctl enable videogen

# Démarrer le service
sudo systemctl start videogen

# Vérifier qu'il tourne correctement (voir section 5)
sudo systemctl status videogen
```

Le service est défini comme suit (extrait) :

- **User/Group :** `videogen`
- **WorkingDirectory :** `/opt/videogen/api`
- **EnvironmentFile :** `/opt/videogen/api/.env`
- **ExecStart :** `/opt/videogen/venv/bin/gunicorn -c gunicorn.conf.py app.main:app`
- **Restart :** `on-failure` avec 3 tentatives max toutes les 60 secondes

---

## 3. Configuration nginx

nginx joue le rôle de reverse proxy : il reçoit les requêtes HTTPS sur le
port 443 et les transmet à Gunicorn qui écoute sur `localhost:8000`.

La configuration se fait en deux temps : d'abord une config HTTP-only pour
permettre à certbot de vérifier le domaine, puis la config SSL complète une
fois le certificat obtenu.

### 3.1 Config nginx HTTP-only (temporaire pour certbot)

```bash
sudo nano /etc/nginx/sites-available/videogen
```

Contenu à coller (config HTTP-only, sans SSL) :

```nginx
# /etc/nginx/sites-available/videogen — config temporaire HTTP-only
# Remplacer <VOTRE_DOMAINE> par le FQDN réel (ex : api.mondomaine.com)

server {
    listen 80;
    server_name <VOTRE_DOMAINE>;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

### 3.2 Activer la config HTTP-only et tester nginx

```bash
# Activer le site (crée un lien symbolique)
sudo ln -s /etc/nginx/sites-available/videogen /etc/nginx/sites-enabled/

# Supprimer le site par défaut si présent
sudo rm -f /etc/nginx/sites-enabled/default

# Vérifier la syntaxe nginx
sudo nginx -t
# Attendu : nginx: configuration file /etc/nginx/nginx.conf syntax is ok

# Démarrer / recharger nginx
sudo systemctl reload nginx
```

### 3.3 Obtenir le certificat Let's Encrypt (certbot)

```bash
# Obtenir le certificat via webroot (nginx reste actif, certbot utilise le port 80)
sudo certbot certonly --webroot -w /var/www/html -d <VOTRE_DOMAINE>
# OU si webroot ne convient pas :
sudo certbot certonly --nginx -d <VOTRE_DOMAINE>

# Vérifier le renouvellement automatique
sudo certbot renew --dry-run
```

### 3.4 Config nginx SSL complète (remplace la config HTTP-only)

Une fois les certificats présents dans `/etc/letsencrypt/live/<VOTRE_DOMAINE>/`,
remplacer intégralement le contenu du fichier de configuration :

```bash
sudo nano /etc/nginx/sites-available/videogen
```

Contenu à coller (config SSL complète) :

```nginx
# /etc/nginx/sites-available/videogen — config SSL définitive
# Remplacer <VOTRE_DOMAINE> par le FQDN réel (ex : api.mondomaine.com)

server {
    listen 80;
    server_name <VOTRE_DOMAINE>;

    # Rediriger tout le HTTP vers HTTPS
    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl;
    server_name <VOTRE_DOMAINE>;

    # ── Certificats Let's Encrypt (générés à l'étape 3.3) ────────────────
    ssl_certificate     /etc/letsencrypt/live/<VOTRE_DOMAINE>/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/<VOTRE_DOMAINE>/privkey.pem;
    include             /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam         /etc/letsencrypt/ssl-dhparams.pem;

    # ── Headers de sécurité ───────────────────────────────────────────────
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=63072000" always;

    # ── Reverse proxy vers Gunicorn ───────────────────────────────────────
    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;

        # Headers nécessaires pour que FastAPI connaisse la vraie IP et le schéma
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;

        # Timeouts : la réponse HTTP est immédiate (202 Accepted) car le
        # pipeline tourne en background — 30s suffisent.
        proxy_connect_timeout  10s;
        proxy_send_timeout     30s;
        proxy_read_timeout     30s;

        # Taille des corps de requête (payload n8n est léger)
        client_max_body_size 1M;
    }

    # ── Health check accessible sans authentification ─────────────────────
    location /health {
        proxy_pass         http://127.0.0.1:8000/health;
        proxy_http_version 1.1;
        proxy_set_header   Host $host;
        access_log         off;   # Éviter de polluer les logs avec les health checks
    }
}
```

### 3.5 Tester et recharger nginx avec la config SSL

```bash
# Vérifier la syntaxe (les fichiers de certificats doivent maintenant exister)
sudo nginx -t
# Attendu : nginx: configuration file /etc/nginx/nginx.conf syntax is ok

# Recharger nginx pour appliquer la config SSL
sudo systemctl reload nginx
```

---

## 4. Variables d'environnement

Toutes les variables sont lues depuis `/opt/videogen/api/.env` par systemd
(`EnvironmentFile`). Le fichier modèle de référence est
`.env.example` dans le dépôt.

| Variable | Obligatoire | Source / Description |
|---|---|---|
| `ENVIRONMENT` | oui | `production` en prod |
| `API_SECRET_KEY` | oui | Token partagé n8n ↔ API. Générer avec `secrets.token_hex(32)` |
| `DEBUG` | non | `false` en production (désactive les routes /docs, /redoc, /openapi.json) |
| `HOST` | non | `0.0.0.0` (défaut) — Gunicorn écoute sur toutes les interfaces |
| `PORT` | non | `8000` (défaut) — port interne Gunicorn |
| `WORKERS` | non | `1` jusqu'à Redis intégré (Jour 2) |
| `LOG_LEVEL` | non | `info` (défaut) — `debug` disponible pour dépannage |
| `ANTHROPIC_API_KEY` | oui | Dashboard Anthropic |
| `CLAUDE_MODEL` | non | `claude-opus-4-6` (défaut) |
| `CLAUDE_MAX_TOKENS` | non | `4096` (défaut) |
| `CLAUDE_MAX_RETRIES` | non | `3` (défaut) |
| `ELEVENLABS_API_KEY` | oui | Dashboard ElevenLabs |
| `ELEVENLABS_MODEL_ID` | non | `eleven_multilingual_v2` (défaut) |
| `ELEVENLABS_DEFAULT_VOICE_ID` | oui | ID du clone vocal dans ElevenLabs |
| `ELEVENLABS_MAX_RETRIES` | non | `2` (défaut) |
| `ELEVENLABS_BACKOFF_BASE` | non | `5.0` secondes (défaut) |
| `KLING_ACCESS_KEY` | oui | Dashboard Kling AI |
| `KLING_SECRET_KEY` | oui | Dashboard Kling AI |
| `KLING_BASE_URL` | non | `https://api.klingai.com` (défaut) |
| `KLING_MODEL` | non | `kling-v1-6` (défaut) |
| `KLING_DURATION` | non | `5` secondes par clip (défaut) |
| `KLING_MAX_PARALLEL_JOBS` | non | `5` (limite API officielle) |
| `KLING_POLLING_INTERVAL` | non | `30.0` secondes (défaut) |
| `KLING_CLIP_TIMEOUT` | non | `600` secondes / 10 min (défaut) |
| `KLING_MAX_RETRIES` | non | `3` (défaut) |
| `PEXELS_API_KEY` | oui | Dashboard Pexels |
| `CREATOMATE_API_KEY` | oui | Dashboard Creatomate |
| `CREATOMATE_TEMPLATE_VERTICAL` | oui | ID template 9:16 créé dans Creatomate |
| `CREATOMATE_TEMPLATE_HORIZONTAL` | oui | ID template 16:9 créé dans Creatomate |
| `CREATOMATE_POLLING_INTERVAL` | non | `15.0` secondes (défaut) |
| `CREATOMATE_RENDER_TIMEOUT` | non | `900` secondes / 15 min (défaut) |
| `CREATOMATE_MAX_RETRIES` | non | `2` (défaut) |
| `GOOGLE_SERVICE_ACCOUNT_PATH` | oui | `/opt/videogen/service_account.json` |
| `GOOGLE_DRIVE_FOLDER_ID` | oui | ID du dossier Drive destination |
| `GOOGLE_SHEETS_ID` | oui | ID du Google Sheets de campagnes |
| `GOOGLE_SHEETS_TAB` | non | `Campagnes` (défaut) |
| `LIBRARY_PATH` | non | `/opt/videogen/library/clips` (défaut) |
| `LIBRARY_INDEX_FILE` | non | `/opt/videogen/library/index.json` (défaut) |
| `LIBRARY_SCORE_THRESHOLD` | non | `0.7` (défaut) |
| `LIBRARY_CLEANUP_DAYS` | non | `90` jours (défaut) |
| `HTTP_TIMEOUT_DEFAULT` | non | `30.0` secondes (défaut) |
| `HTTP_TIMEOUT_VIDEO_GEN` | non | `600.0` secondes — timeout global pipeline (défaut) |
| `HTTP_MAX_CONNECTIONS` | non | `20` (défaut) |
| `HTTP_MAX_KEEPALIVE` | non | `10` (défaut) |
| `N8N_WEBHOOK_NOTIFICATION_URL` | oui | URL webhook n8n pour les callbacks |
| `API_CREDIT_ALERT_THRESHOLD` | non | `0.20` (défaut) — alerte si crédits < 20% |
| `LOGO_URL` | non | URL du logo pour les rendus Creatomate |

---

## 5. Vérification du déploiement

### 5.1 Statut du service systemd

```bash
sudo systemctl status videogen
```

Sortie attendue (extrait) :

```
● videogen.service - VideoGen API — Système d'automatisation pub vidéo
     Loaded: loaded (/etc/systemd/system/videogen.service; enabled; ...)
     Active: active (running) since ...
   Main PID: XXXX (gunicorn)
```

En cas de problème, lire les logs :

```bash
sudo journalctl -u videogen -n 50 --no-pager
```

### 5.2 Health check local

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```

Réponse attendue :

```json
{
    "status": "ok",
    "version": "1.0.0",
    "environment": "production"
}
```

> En production, les routes `/docs`, `/redoc` et `/openapi.json` sont
> désactivées (`ENVIRONMENT=production`). Seul `/health` est public.

### 5.3 Health check via nginx (HTTPS)

```bash
curl -s https://<VOTRE_DOMAINE>/health | python3 -m json.tool
```

### 5.4 Test du endpoint POST /generate

```bash
# Remplacer <VOTRE_TOKEN_SECRET> par la valeur de API_SECRET_KEY dans .env
curl -s -X POST https://<VOTRE_DOMAINE>/generate \
  -H "Authorization: Bearer <VOTRE_TOKEN_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": "00000000-0000-0000-0000-000000000001",
    "sheets_row": {
      "row_id": "test-row-1",
      "script": "Ceci est un test de déploiement.",
      "format": "vertical",
      "strategy": "B",
      "duration": 30,
      "voice_id": "test-voice",
      "music_url": null,
      "cta": "Découvrez maintenant"
    },
    "webhook_url": null
  }' | python3 -m json.tool
```

Réponse attendue (202 Accepted) :

```json
{
    "job_id": "00000000-0000-0000-0000-000000000001",
    "status": "pending",
    "message": "Job créé. Pipeline démarré en arrière-plan.",
    "status_url": "https://<VOTRE_DOMAINE>/status/00000000-0000-0000-0000-000000000001"
}
```

### 5.5 Test du endpoint GET /status

```bash
curl -s https://<VOTRE_DOMAINE>/status/00000000-0000-0000-0000-000000000001 \
  -H "Authorization: Bearer <VOTRE_TOKEN_SECRET>" | python3 -m json.tool
```

### 5.6 Test d'authentification invalide (doit retourner 401)

```bash
curl -s -o /dev/null -w "%{http_code}" https://<VOTRE_DOMAINE>/generate \
  -H "Authorization: Bearer mauvais-token" \
  -H "Content-Type: application/json" \
  -d '{}'
# Attendu : 401
```

---

## 6. Commandes utiles

### Logs

```bash
# Logs en temps réel (Ctrl+C pour quitter)
sudo journalctl -u videogen -f

# 100 dernières lignes
sudo journalctl -u videogen -n 100 --no-pager

# Logs depuis un timestamp précis
sudo journalctl -u videogen --since "2026-02-28 10:00:00" --no-pager

# Logs nginx access
sudo tail -f /var/log/nginx/access.log

# Logs nginx error
sudo tail -f /var/log/nginx/error.log
```

### Redémarrage

```bash
# Redémarrer l'API (rechargement du .env inclus)
sudo systemctl restart videogen

# Recharger nginx sans interruption de service
sudo systemctl reload nginx

# Redémarrer nginx complètement
sudo systemctl restart nginx
```

### Statut général

```bash
# Statut service API
sudo systemctl status videogen

# Statut nginx
sudo systemctl status nginx

# Voir les processus Gunicorn actifs
ps aux | grep gunicorn

# Vérifier que le port 8000 est bien écouté en local
ss -tlnp | grep 8000
```

---

## 7. Mise à jour

Procédure pour déployer une nouvelle version depuis GitHub :

```bash
# 1. Se placer dans le répertoire du dépôt
cd /opt/videogen/api

# 2. Récupérer les dernières modifications
sudo -u videogen git fetch origin
sudo -u videogen git pull origin main

# 3. Vérifier que les dépendances sont à jour
sudo -u videogen /opt/videogen/venv/bin/pip install -e /opt/videogen/api

# 4. Si le fichier systemd a changé, le réinstaller
sudo cp /opt/videogen/api/systemd/videogen.service /etc/systemd/system/videogen.service
sudo systemctl daemon-reload

# 5. Redémarrer le service
sudo systemctl restart videogen

# 6. Vérifier que tout fonctionne
sudo systemctl status videogen
curl -s http://localhost:8000/health | python3 -m json.tool
```

> **Tip :** noter le SHA du commit avant la mise à jour pour pouvoir rollback :
> `git rev-parse HEAD` (à exécuter avant le `git pull`).

---

## 8. Rollback

### 8.1 Rollback vers le commit précédent

```bash
# 1. Identifier le commit à restaurer
cd /opt/videogen/api
sudo -u videogen git log --oneline -10

# 2. Arrêter le service proprement
sudo systemctl stop videogen

# 3. Revenir au commit cible (remplacer <SHA_COMMIT> par le hash souhaité)
sudo -u videogen git checkout <SHA_COMMIT>

# 4. Réinstaller les dépendances correspondantes
sudo -u videogen /opt/videogen/venv/bin/pip install -e /opt/videogen/api

# 5. Redémarrer
sudo systemctl start videogen

# 6. Vérifier
sudo systemctl status videogen
curl -s http://localhost:8000/health
```

### 8.2 Rollback si le service ne démarre plus du tout

```bash
# Vérifier les erreurs de démarrage
sudo journalctl -u videogen -n 50 --no-pager

# Causes fréquentes :
# - Variable manquante dans .env → l'API refuse de démarrer (validation Pydantic)
# - Dépendance manquante → ImportError dans les logs
# - Port 8000 déjà utilisé → "Address already in use"

# Diagnostiquer les erreurs de configuration
sudo -u videogen /opt/videogen/venv/bin/python -c "from app.config import get_settings; get_settings()"

# Si le .env est en cause, restaurer une version précédente
sudo nano /opt/videogen/api/.env
sudo systemctl start videogen
```

### 8.3 Rollback nginx

```bash
# Si nginx refuse de démarrer après une modification de la config
sudo nginx -t                          # Affiche l'erreur exacte
sudo nano /etc/nginx/sites-available/videogen   # Corriger la config
sudo nginx -t && sudo systemctl reload nginx
```

---

## Annexe : Arborescence de déploiement

```
/opt/videogen/
├── api/                          # Dépôt Git cloné
│   ├── app/
│   │   └── main.py               # Endpoints : /health, /generate, /status/{id}
│   ├── gunicorn.conf.py          # Config Gunicorn (WORKERS, PORT, timeouts)
│   ├── systemd/
│   │   └── videogen.service      # Copié dans /etc/systemd/system/
│   ├── .env                      # Secrets — NE PAS committer
│   └── .env.example              # Modèle de référence
├── venv/                         # Virtualenv Python 3.12
│   └── bin/gunicorn              # ExecStart du service systemd
├── service_account.json          # Compte de service Google (chmod 600)
└── library/
    ├── clips/                    # Bibliothèque clips B-roll (Stratégie B)
    └── index.json                # Index de la bibliothèque
```
