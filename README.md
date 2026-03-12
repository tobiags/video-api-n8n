# VideoGen — AI Video Ad Automation

> Pipeline automatisé de génération de publicités vidéo par intelligence artificielle, du script à la livraison sur Google Drive.

---

## Vue d'ensemble

VideoGen transforme une ligne Google Sheets en une vidéo publicitaire complète sans intervention humaine.

```
Google Sheets (Statut = ok)
    → Script analysé par Claude AI
    → Voix off générée par ElevenLabs
    → Clips B-roll via Kling AI / Pexels
    → Vidéo assemblée par Creatomate
    → Livrée automatiquement sur Google Drive
```

Temps moyen de génération : **8 à 15 minutes** par vidéo.
Coût moyen par vidéo (stratégie B) : **~2,50 $** à partir du 2e mois.

---

## Fonctionnalités

- **Analyse IA du script** — Claude AI découpe le script en scènes, génère les timings et les prompts B-roll
- **Voix off naturelle** — ElevenLabs avec synchronisation mot à mot pour les sous-titres
- **B-roll intelligent** — Cascade : bibliothèque locale → Pexels (gratuit) → Kling AI (génératif)
- **Assemblage automatique** — Creatomate assemble voix, clips, sous-titres, musique, logo et CTA
- **Formats flexibles** — 9:16 (vertical), 16:9 (horizontal), durée libre de 15 à 90 secondes
- **Queue de jobs** — jusqu'à 2 pipelines en parallèle, les suivants s'empilent en file d'attente
- **Dashboard de monitoring** — interface temps réel pour suivre chaque étape du pipeline
- **Catalogue de voix** — écoute et sélection des voix ElevenLabs depuis le dashboard
- **Tracking d'erreurs** — intégration Sentry pour alertes en production

---

## Stack technique

| Composant | Technologie |
|-----------|-------------|
| API Backend | Python 3.14 · FastAPI 0.115 · Pydantic v2 |
| Serveur | Uvicorn / Gunicorn · Docker · Coolify |
| Proxy | Traefik |
| Orchestration | n8n (workflows no-code) |
| IA Script | Anthropic Claude claude-opus-4-6 |
| IA Voix | ElevenLabs |
| IA Vidéo | Kling AI (JWT auth) |
| Stock vidéo | Pexels API |
| Assemblage | Creatomate |
| Stockage | Google Drive · Google Sheets |
| Monitoring | Sentry |

---

## Architecture

```
┌─────────────────┐     webhook      ┌─────────────┐
│  Google Sheets  │ ─────────────▶  │     n8n     │
│  (déclencheur)  │                  │  (workflow) │
└─────────────────┘                  └──────┬──────┘
                                            │ POST /generate
                                            ▼
                                    ┌─────────────┐
                                    │  FastAPI    │
                                    │  (backend)  │
                                    └──────┬──────┘
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    ▼                      ▼                       ▼
             ┌──────────┐          ┌────────────┐         ┌──────────────┐
             │ Claude AI │          │ ElevenLabs │         │  Kling AI /  │
             │ (script)  │          │  (voix)    │         │  Pexels      │
             └──────────┘          └────────────┘         └──────────────┘
                                           │
                                           ▼
                                    ┌────────────┐
                                    │ Creatomate │
                                    │ (assemblage)│
                                    └──────┬─────┘
                                           │
                                           ▼
                                    ┌────────────┐
                                    │Google Drive│
                                    │ + Sheets   │
                                    └────────────┘
```

---

## Structure du projet

```
video-api/
├── app/
│   ├── main.py           # FastAPI : endpoints, pipeline, queue
│   ├── claude.py         # Analyse script → structure JSON
│   ├── elevenlabs.py     # Génération voix off + timestamps
│   ├── kling.py          # Génération clips B-roll IA
│   ├── library.py        # Cascade B-roll (stratégie A/B)
│   ├── creatomate.py     # Assemblage vidéo finale
│   ├── models.py         # Schémas Pydantic
│   ├── config.py         # Configuration centralisée
│   ├── errors.py         # Gestion d'erreurs unifiée
│   ├── monitor_html.py   # Dashboard de monitoring
│   └── voices.py         # Catalogue voix ElevenLabs
├── tests/
│   ├── test_claude.py
│   ├── test_elevenlabs.py
│   ├── test_kling.py
│   ├── test_library.py
│   ├── test_creatomate.py
│   ├── test_integration.py
│   └── test_config.py
├── docs/
│   ├── deployment.md     # Guide déploiement VPS
│   ├── n8n-setup.md      # Configuration workflows n8n
│   └── guide-client.md   # Manuel d'utilisation client
├── n8n/
│   └── workflow_videogen.json
├── Dockerfile
├── gunicorn.conf.py
└── pyproject.toml
```

---

## Déploiement

### Prérequis

- VPS Ubuntu 22.04+ (2 Go RAM minimum)
- [Coolify](https://coolify.io) installé
- Clés API : Anthropic, ElevenLabs, Kling AI, Pexels, Creatomate
- Compte Google Cloud (Drive + Sheets API)

### Variables d'environnement requises

```env
API_SECRET_KEY=         # Clé secrète partagée n8n ↔ API
ANTHROPIC_API_KEY=      # Claude AI
ELEVENLABS_API_KEY=     # ElevenLabs
ELEVENLABS_DEFAULT_VOICE_ID=
KLING_ACCESS_KEY=       # Kling AI
KLING_SECRET_KEY=
PEXELS_API_KEY=         # Pexels
CREATOMATE_API_KEY=     # Creatomate
GOOGLE_DRIVE_FOLDER_ID= # Dossier Drive de livraison
GOOGLE_SERVICE_ACCOUNT= # JSON service account (base64)
SENTRY_DSN=             # Sentry (optionnel)
```

### Lancer en local

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Lancer les tests

```bash
pytest tests/ -v
```

---

## Dashboard de monitoring

Accessible via `/monitor?key=VOTRE_CLE`

- **Onglet Pipelines** — suivi temps réel de chaque vidéo en cours
- **Onglet Voix** — catalogue avec lecteur audio et copie d'ID

---

## Endpoints API

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `POST` | `/generate` | Lance un pipeline de génération |
| `GET` | `/jobs` | Liste tous les jobs en mémoire |
| `GET` | `/status/{job_id}` | Statut d'un job spécifique |
| `GET` | `/voices` | Catalogue des voix disponibles |
| `GET` | `/monitor` | Dashboard HTML |
| `GET` | `/docs` | Documentation Swagger |

---

## Stratégies B-roll

| Stratégie | Source clips | Coût estimé/vidéo |
|-----------|-------------|-------------------|
| **A** | Kling AI uniquement | ~6–14 $ |
| **B** | Bibliothèque → Pexels → Kling | ~2,50 $ (mois 2+) |

---

## Licence

Projet privé — tous droits réservés.
