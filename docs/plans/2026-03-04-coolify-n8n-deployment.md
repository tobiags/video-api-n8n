# Coolify Deployment + n8n Workflow Finalization — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy the video-api on the VPS via Coolify (Dockerfile from GitHub), and finalize the n8n workflow with correct notification types and without the redundant Drive upload step.

**Architecture:** Coolify builds the API container from the GitHub repo's Dockerfile. n8n and the API communicate via Docker internal network (no public exposure of port 8000). The API already handles the Google Drive upload itself and sends the final `drive_url` back to n8n via webhook callback — n8n does NOT need to upload to Drive.

**Tech Stack:** Docker (python:3.12-slim + gunicorn), Coolify, n8n, JSON workflow import, Google Sheets/Drive OAuth2.

---

## Context

### Internal Docker networking (Coolify)

When two services belong to the same Coolify project, they share a Docker network. DNS resolution works by service name:

- n8n → API: `http://<api-service-name>:8000`
- API → n8n webhook: `http://<n8n-service-name>:5678/webhook/videogen-callback`

The API service name is visible in **Coolify → Service → General → Service Name**.

### Bugs found in `n8n/workflow_videogen.json`

| Location | Bug | Fix |
|---|---|---|
| `Check notification type` Switch node | Uses `"completed"` but `NotificationType.SUCCESS = "success"` | Change to `"success"` |
| `Upload Google Drive` node | Entirely wrong — API already uploads to Drive | Remove node entirely |
| `Update Sheets Livré` | Uses `$json.webViewLink` from Drive upload | Use `$('Webhook Callback').item.json.body.drive_url` |

### How the API notification works

The API sends a `POST webhook_url` with a `NotificationPayload`:
```json
{
  "type": "success",
  "job_id": "uuid",
  "row_id": "row_12",
  "message": "Job terminé avec succès",
  "drive_url": "https://drive.google.com/file/d/..."
}
```

The `drive_url` is already the final Google Drive URL. n8n just writes it to Sheets.

---

## Task 1: Create Dockerfile

**Files:**
- Create: `Dockerfile`

**Step 1: Create the file**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["gunicorn", "-c", "gunicorn.conf.py", "app.main:app"]
```

**Step 2: Verify `gunicorn.conf.py` exists**

Run: `ls gunicorn.conf.py`
Expected: file listed (already exists from Day 1).

**Step 3: Commit**

```bash
git add Dockerfile
git commit -m "feat: add Dockerfile for Coolify deployment"
```

---

## Task 2: Create .dockerignore

**Files:**
- Create: `.dockerignore`

**Step 1: Create the file**

```
.env
.env.*
tests/
__pycache__/
**/__pycache__/
*.pyc
*.pyo
.git/
.gitignore
docs/
.pytest_cache/
.ruff_cache/
*.md
```

**Step 2: Commit**

```bash
git add .dockerignore
git commit -m "feat: add .dockerignore"
```

---

## Task 3: Fix and finalize n8n/workflow_videogen.json

**Files:**
- Modify: `n8n/workflow_videogen.json`

Three bugs to fix (see Context section above). The corrected file is specified in full below.

**Step 1: Fix the Switch node**

In node `1a2b3c4d-0006`, change:
```json
"rules": [
  { "value": "completed" },
  { "value": "blocking_error" }
]
```
To:
```json
"rules": [
  { "value": "success" },
  { "value": "blocking_error" }
]
```

**Step 2: Remove the Upload Google Drive node**

Delete the entire node object with `"id": "1a2b3c4d-0007-0007-0007-000000000007"` (name: "Upload Google Drive").

**Step 3: Fix Update Sheets Livré node**

In node `1a2b3c4d-0008`, change:
```json
"Lien output": "={{ $json.webViewLink }}"
```
To:
```json
"Lien output": "={{ $('Webhook Callback').item.json.body.drive_url }}"
```

**Step 4: Fix connections**

Remove the `"Upload Google Drive"` entry from connections entirely.

Change `"Check notification type"` output[0] to point directly to `"Update Sheets Livré"`:
```json
"Check notification type": {
  "main": [
    [{ "node": "Update Sheets Livré", "type": "main", "index": 0 }],
    [{ "node": "Update Sheets Erreur", "type": "main", "index": 0 }]
  ]
}
```

**Step 5: Verify the full corrected JSON**

After edits, the `connections` block must contain exactly these entries:
- `"Sheets Trigger"` → `"Filter status=OK"`
- `"Filter status=OK"` → `"Update status En cours"`
- `"Update status En cours"` → `"POST /generate"`
- `"Webhook Callback"` → `"Check notification type"`
- `"Check notification type"` → output[0]: `"Update Sheets Livré"`, output[1]: `"Update Sheets Erreur"`
- `"Update Sheets Livré"` → `"Respond to Webhook"`
- `"Update Sheets Erreur"` → `"Respond to Webhook"`

**NO "Upload Google Drive" entry in connections.**

**Step 6: Commit**

```bash
git add n8n/workflow_videogen.json
git commit -m "fix: correct n8n workflow — success type, remove redundant Drive upload, fix drive_url field"
```

---

## Task 4: Update docs/n8n-setup.md

**Files:**
- Modify: `docs/n8n-setup.md`

**Step 1: Update section 1 (Variables d'environnement n8n)**

Update the variables table to reflect Coolify internal URLs:

| Variable | Valeur (Coolify) | Description |
|---|---|---|
| `GOOGLE_SHEETS_ID` | `1BxiMVs0...` | ID du Google Sheet (dans l'URL) |
| `GOOGLE_DRIVE_FOLDER_ID` | `1AbcXYZ...` | ID du dossier Drive de destination |
| `VIDEOGEN_API_URL` | `http://<api-service-name>:8000` | URL **interne Docker** de l'API VideoGen |
| `VIDEOGEN_API_SECRET` | `votre-clé-secrète` | Valeur de `API_SECRET_KEY` dans Coolify env vars |
| `N8N_WEBHOOK_URL` | `http://<n8n-service-name>:5678` | URL **interne Docker** de n8n (pour le callback de l'API) |

Add note: `<api-service-name>` and `<n8n-service-name>` are visible in Coolify → Service → General.

**Step 2: Fix section 4 (Structure du workflow) diagram**

Change:
```
[Check type]           ←── "completed" → Drive | "blocking_error" → Erreur
       ↓                              ↓
[Upload Drive]    [Update "Erreur"]
       ↓
[Update "Livré"]       ←── Sheets: Statut="Livré" + Lien output=URL Drive
```

To:
```
[Check type]           ←── "success" → Livré | "blocking_error" → Erreur
       ↓                              ↓
[Update "Livré"]  [Update "Erreur"]
←── Sheets: Statut="Livré" + Lien output=drive_url (fourni par l'API)
```

Add note: L'API gère elle-même l'upload Google Drive et envoie `drive_url` dans le callback. n8n écrit simplement cette URL dans Sheets.

**Step 3: Add new section "Déploiement Coolify" (before section 7 "Premier test")**

````markdown
## 6b. Déploiement sur Coolify

### Prérequis
- Repository GitHub pushé avec Dockerfile
- Coolify installé sur le VPS avec n8n déjà déployé

### Étapes dans Coolify

1. **Coolify → New Resource → Application**
2. **Source :** GitHub → sélectionner le repo `tobiags/video-api-n8n`, branche `main`
3. **Build Pack :** Dockerfile (auto-détecté)
4. **Ports :** `8000` → cocher **Private** (interne uniquement, ne pas exposer publiquement)
5. **Service Name :** noter ce nom — c'est le nom DNS interne (ex: `videogen-api`)
6. **Environment Variables :** ajouter toutes les variables depuis `.env.example` :

| Variable | Valeur |
|---|---|
| `ENVIRONMENT` | `production` |
| `WORKERS` | `1` |
| `API_SECRET_KEY` | Générer avec : `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ANTHROPIC_API_KEY` | `sk-ant-...` |
| `ELEVENLABS_API_KEY` | `...` |
| `KLING_ACCESS_KEY` | `...` |
| `KLING_SECRET_KEY` | `...` |
| `PEXELS_API_KEY` | `...` |
| `CREATOMATE_API_KEY` | `...` |
| `GOOGLE_SERVICE_ACCOUNT_PATH` | `/opt/videogen/service_account.json` (voir note ci-dessous) |
| `GOOGLE_DRIVE_FOLDER_ID` | `...` |
| `GOOGLE_SHEETS_ID` | `...` |
| `N8N_WEBHOOK_NOTIFICATION_URL` | `http://<n8n-service-name>:5678/webhook/videogen-callback` |
| `LOGO_URL` | `https://ton-cdn.com/logo.png` |

7. **Deploy** → Coolify build l'image et démarre le container

### Note : Google Service Account

Le fichier JSON du compte de service Google doit être monté dans le container.
Options :
- **Volume Coolify** : créer un volume avec le fichier JSON, le monter sur `/opt/videogen/`
- **Variable d'env** : encoder le JSON en base64, décoder au démarrage (nécessite script entrypoint)

La méthode la plus simple : créer le fichier via Coolify → Service → Volumes.

### Réseau interne

Depuis n8n, l'API est accessible via `http://<api-service-name>:8000`.
Depuis l'API, le webhook n8n est accessible via `http://<n8n-service-name>:5678/webhook/videogen-callback`.

Ces deux noms DNS sont visibles dans **Coolify → Service → General → Service Name**.
````

**Step 4: Commit**

```bash
git add docs/n8n-setup.md
git commit -m "docs: update n8n-setup for Coolify internal networking and fixed workflow"
```

---

## Task 5: Push to GitHub

**Step 1: Push**

```bash
git push origin main
```

If Coolify is configured with auto-deploy on push, the build starts automatically.
Otherwise: Coolify → Service → Deploy.

**Step 2: Verify build logs**

In Coolify → Service → Deployments → latest deploy → view logs.
Expected: `Successfully built image`, `Container started`, health check passing.

**Step 3: Import workflow in n8n**

1. n8n → Workflows → **+ New** → **Import from file/clipboard**
2. Paste content of `n8n/workflow_videogen.json`
3. Click Import
4. Set n8n variables (Settings → Variables) as documented in n8n-setup.md section 1
5. Open workflow → **Active** (toggle top right)
6. Verify webhook is active (Webhook Callback node should show its URL)

**Step 4: Smoke test**

```bash
# Test the API health endpoint from outside (if accessible via Coolify domain)
curl https://your-coolify-domain/health

# Or test from inside (via n8n HTTP Request node):
# Add a manual test node in n8n that calls GET http://<api-service-name>:8000/health
# Expected: {"status": "ok", "version": "1.0.0"}
```

---

## Summary of all commits

```
feat: add Dockerfile for Coolify deployment
feat: add .dockerignore
fix: correct n8n workflow — success type, remove redundant Drive upload, fix drive_url field
docs: update n8n-setup for Coolify internal networking and fixed workflow
```

---

## Checklist before going live

- [ ] Dockerfile builds without error locally (`docker build -t videogen-api .`)
- [ ] `.dockerignore` excludes `.env` (never commit secrets)
- [ ] Switch node uses `"success"` (not `"completed"`)
- [ ] No "Upload Google Drive" node in workflow
- [ ] `drive_url` used in Update Sheets Livré (not `webViewLink`)
- [ ] Coolify: port 8000 is **not** publicly exposed
- [ ] Coolify: all env vars set (especially `API_SECRET_KEY` and Google credentials)
- [ ] n8n: `VIDEOGEN_API_URL` = internal Docker URL (e.g. `http://videogen-api:8000`)
- [ ] n8n: `N8N_WEBHOOK_URL` = internal Docker URL (e.g. `http://n8n:5678`)
- [ ] n8n: `VIDEOGEN_API_SECRET` = same value as `API_SECRET_KEY` in Coolify
