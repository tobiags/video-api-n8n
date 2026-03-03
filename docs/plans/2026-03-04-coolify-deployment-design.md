# Design — Déploiement Coolify + n8n Workflow (video-api)

**Date :** 2026-03-04
**Contexte :** Déployer l'API VideoGen sur le VPS via Coolify (GitHub → Dockerfile), et finaliser le workflow n8n pour qu'il communique avec l'API en interne.

---

## Architecture cible

```
GitHub repo (tobiags/video-api-n8n)
        ↓  Coolify pull + build Dockerfile
  Container: videogen-api (port 8000, réseau interne)
        ↓  réseau Docker interne Coolify
  Container: n8n (déjà déployé)

  n8n  →  POST http://videogen-api:8000/generate
  API  →  POST http://n8n:5678/webhook/videogen-callback
```

---

## Composants à créer/modifier

### 1. Dockerfile (nouveau)
- Base : `python:3.12-slim`
- Copie `requirements.txt` → `pip install`
- Copie le code app
- Expose port `8000`
- CMD : `gunicorn -c gunicorn.conf.py app.main:app`

### 2. .dockerignore (nouveau)
- Exclure : `.env`, `tests/`, `__pycache__`, `.git`, `docs/`, `*.pyc`

### 3. n8n/workflow_videogen.json (finaliser)
- URLs internes Docker : `http://videogen-api:8000` (à paramétrer via variable n8n)
- Webhook callback : `http://n8n:5678/webhook/videogen-callback`
- Nœuds complets avec vraies connexions

### 4. docs/n8n-setup.md (mettre à jour)
- Section spécifique Coolify : noms de service internes
- Comment trouver le nom DNS interne du container dans Coolify
- Variables d'environnement n8n à configurer

---

## Variables d'environnement (Coolify UI)

Toutes les vars du `.env.example` saisies dans **Coolify → Service → Environment Variables** :
- `ENVIRONMENT=production`
- `WORKERS=1`
- `API_SECRET_KEY=<généré>`
- Toutes les clés API (Anthropic, ElevenLabs, Kling, Pexels, Creatomate, Google)

---

## Réseau interne Coolify

Coolify place les services d'un même projet dans un réseau Docker partagé.
- Nom DNS de l'API depuis n8n : `<service-name>` (visible dans Coolify → Service → General)
- Pas d'exposition publique du port 8000
- n8n et l'API communiquent via ce réseau interne

---

## Sécurité

- Port 8000 : non exposé publiquement (interne uniquement)
- `API_SECRET_KEY` : partagé entre n8n et l'API via Coolify env vars
- Pas de `.env` sur le serveur — tout géré par Coolify

---

## Livrable final

| Fichier | Action |
|---|---|
| `Dockerfile` | Créer |
| `.dockerignore` | Créer |
| `n8n/workflow_videogen.json` | Finaliser avec URLs internes |
| `docs/n8n-setup.md` | Mettre à jour section Coolify |
| GitHub push | Déclenche auto-deploy Coolify |
