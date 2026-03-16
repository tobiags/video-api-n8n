# Preuves de livraison — Projet VideoGen
**Automatisation de création publicitaire vidéo par IA**

---

## Résumé du projet livré

Pipeline complet de génération automatique de vidéos publicitaires, de la commande (Google Sheets) jusqu'à la livraison (Google Drive), sans intervention humaine.

**Stack livré :** Python 3.14 · FastAPI · Docker · Coolify · n8n · Claude AI · ElevenLabs · Kling AI · Pexels · Creatomate · Google Drive/Sheets

---

## Preuve 1 — Dépôt Git public avec historique complet

**URL :** https://github.com/tobiags/video-api-n8n

**50 commits documentés**, du premier squelette jusqu'aux corrections de production :

| Commit | Description |
|--------|-------------|
| `22acb6b` | feat: claude.py — analyse de script avec retry |
| `c7ca58c` | feat: elevenlabs.py — voiceover + timestamps |
| `74cf971` | feat: kling.py — génération clips avec semaphore et fallback |
| `acaea16` | feat: library.py — cascade B (library → pexels → kling) |
| `689be89` | feat: creatomate.py — assemblage vidéo avec sync sous-titres |
| `1badc26` | feat: pipeline global avec timeout + test d'intégration |
| `695c9b9` | feat: Dockerfile pour déploiement Coolify |
| `310a5b4` | feat: Sentry error tracking |
| `93068b1` | feat: dashboard /monitor + endpoint /jobs |
| `4aeffdc` | feat: onglet Voix — catalogue ElevenLabs avec lecteur audio |
| `afe0ba0` | feat: queue de jobs + cohérence visuelle Claude |
| `2c96c62` | feat: redesign dashboard (veed.io aesthetic + lien direct client) |

---

## Preuve 2 — Application en production

**Dashboard live :** http://ys4o0cosg48gk0o4g4o8o4kw.95.217.220.12.sslip.io/monitor

**API en ligne :** http://ys4o0cosg48gk0o4g4o8o4kw.95.217.220.12.sslip.io/docs

Hébergée sur VPS Hetzner via Coolify + Traefik, container Docker actif depuis le déploiement initial.

---

## Preuve 3 — Code source livré (8 458 lignes)

### Backend API — `app/`

| Fichier | Rôle | Lignes |
|---------|------|--------|
| `main.py` | Serveur FastAPI, endpoints, pipeline, queue | 729 |
| `claude.py` | Analyse script → structure JSON via Claude AI | 178 |
| `elevenlabs.py` | Génération voix off + timestamps mot à mot | 196 |
| `kling.py` | Génération clips B-roll IA (semaphore 5 jobs) | 238 |
| `library.py` | Cascade B-roll : bibliothèque → Pexels → Kling | 184 |
| `creatomate.py` | Assemblage final vidéo + sous-titres + musique | 294 |
| `models.py` | Schémas Pydantic (validation entrées/sorties) | 410 |
| `config.py` | Configuration centralisée + secrets | 204 |
| `errors.py` | Gestion d'erreurs unifiée | 247 |
| `monitor_html.py` | Dashboard de monitoring (HTML/CSS/JS) | 769 |
| `voices.py` | Catalogue de voix ElevenLabs | 112 |

### Tests automatisés — `tests/`

| Fichier | Couverture |
|---------|------------|
| `test_config.py` | 15 tests · configuration et validation |
| `test_claude.py` | Analyse script, retry, JSON invalide |
| `test_elevenlabs.py` | Génération audio, retry backoff exponentiel |
| `test_kling.py` | Génération clips, semaphore, fallback Pexels |
| `test_library.py` | Cascade B-roll stratégie A et B |
| `test_creatomate.py` | Assemblage vidéo, gestion erreurs API |
| `test_integration.py` | Pipeline bout-en-bout (mock complet) |

### Documentation — `docs/`

| Fichier | Contenu |
|---------|---------|
| `deployment.md` | Guide déploiement VPS complet |
| `n8n-setup.md` | Configuration workflow n8n |
| `guide-client.md` | Manuel d'utilisation client |
| `VideoGen_Sheets_Setup.xlsx` | Template Google Sheets |
| `plans/` | 3 documents de conception technique |

---

## Preuve 4 — Pipeline fonctionnel de bout en bout

Flux complet implémenté et testé :

```
Google Sheets (Statut = ok)
        ↓
    n8n webhook
        ↓
POST /generate (FastAPI)
        ↓
   🤖 Claude AI
   → analyse script
   → génère structure JSON (scènes, timings, B-roll prompts)
        ↓
   🎙️ ElevenLabs
   → voix off MP3
   → timestamps mot à mot pour sous-titres
        ↓
   🎬 Kling AI / Pexels / Bibliothèque
   → clips B-roll (stratégie A ou B au choix)
   → semaphore 5 jobs parallèles max
        ↓
   ⚙️ Creatomate
   → assemblage vidéo finale
   → sous-titres synchronisés mot à mot
   → musique de fond + logo + CTA
        ↓
   ☁️ Google Drive
   → upload automatique
   → lien partageable retourné
        ↓
   n8n callback
   → mise à jour Google Sheets (colonne Lien output)
   → notification
```

---

## Preuve 5 — Fonctionnalités livrées vs demandées

| Fonctionnalité demandée | Statut | Preuve |
|------------------------|--------|--------|
| Déclenchement depuis Google Sheets | ✅ Livré | Workflow n8n `LANCEMENT TACHES` |
| Génération script/structure par Claude AI | ✅ Livré | `app/claude.py` |
| Voix off IA (ElevenLabs) | ✅ Livré | `app/elevenlabs.py` |
| Clips B-roll IA (Kling) | ✅ Livré | `app/kling.py` |
| Fallback Pexels si Kling échoue | ✅ Livré | `app/library.py` |
| Assemblage vidéo final (Creatomate) | ✅ Livré | `app/creatomate.py` |
| Livraison automatique Google Drive | ✅ Livré | `app/main.py` |
| Sous-titres synchronisés mot à mot | ✅ Livré | `app/creatomate.py` |
| Dashboard de monitoring temps réel | ✅ Livré | `app/monitor_html.py` + `/monitor` |
| Catalogue voix avec écoute + copie ID | ✅ Livré | Onglet Voix du dashboard |
| Queue de jobs (limite concurrence) | ✅ Livré | `asyncio.Semaphore` dans `main.py` |
| Gestion d'erreurs + Sentry | ✅ Livré | `app/errors.py` + Sentry SDK |
| Déploiement production Docker/VPS | ✅ Livré | Coolify + Traefik actif |
| Workflows n8n complets | ✅ Livré | `LANCEMENT TACHES` + `FINALISATION` |
| Documentation technique | ✅ Livré | `docs/` (deployment, n8n-setup) |
| Guide d'utilisation client | ✅ Livré | `docs/guide-client.md` |
| Format vidéo configurable (9:16, 16:9) | ✅ Livré | Colonne Format Google Sheets |
| Durée vidéo libre (15–90s) | ✅ Livré | Colonne Durée Google Sheets |
| Cohérence visuelle B-roll (genre/âge) | ✅ Livré | System prompt Claude Rules 6&7 |

---

## Preuve 6 — Corrections post-livraison assurées

Bugs remontés par le client, corrigés et redéployés :

| Bug | Commit | Correction |
|-----|--------|------------|
| Caractères `\r\n` dans voice_id (Google Sheets) | `620b723` | Validator Pydantic `strip()` |
| Bouton "Copier ID" inactif en HTTP | `620b723` | `execCommand` au lieu de `navigator.clipboard` |
| Workflow FINALISATION — Switch ne routait pas | `afe0ba0` | Correction condition `$json.body.type` |
| Workflow FINALISATION — Sheets non mis à jour | `afe0ba0` | `matchingColumns: row_number` |
| Videos avec mauvais genre (homme au lieu de femme) | `afe0ba0` | Règles 6&7 system prompt Claude |
| 5-6 jobs simultanés crashaient l'app | `afe0ba0` | `asyncio.Semaphore(2)` |
| Dashboard inaccessible sans HTTPS | `883d6d9` | Auth via `?key=` query param |

---

*Dépôt GitHub : https://github.com/tobiags/video-api-n8n*
*Application live : http://ys4o0cosg48gk0o4g4o8o4kw.95.217.220.12.sslip.io/monitor*
*Date de génération de ce document : 2026-03-12*
