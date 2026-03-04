# Guide de configuration n8n — VideoGen Pipeline

## Prérequis

- n8n installé (self-hosted ou cloud) — version ≥ 1.0
- Accès à Google Sheets et Google Drive (OAuth2)
- API VideoGen déployée et accessible (voir `docs/deployment.md`)

---

## 1. Variables d'environnement n8n

Dans l'interface n8n → **Settings → Variables**, définir :

| Variable | Valeur | Description |
|---|---|---|
| `GOOGLE_SHEETS_ID` | `1BxiMVs0...` | ID du Google Sheet (dans l'URL) |
| `GOOGLE_DRIVE_FOLDER_ID` | `1AbcXYZ...` | ID du dossier Drive de destination |
| `VIDEOGEN_API_URL` | `http://<api-service-name>:8000` | URL interne Docker de l'API VideoGen (voir section Coolify ci-dessous) |
| `VIDEOGEN_API_SECRET` | `votre-clé-secrète` | Valeur de `API_SECRET_KEY` dans Coolify env vars |
| `N8N_WEBHOOK_URL` | `http://<n8n-service-name>:5678` | URL interne Docker de n8n — utilisée par l'API pour le callback |

> **Déploiement Coolify :** `<api-service-name>` et `<n8n-service-name>` sont visibles dans **Coolify → Service → General → Service Name**. Les deux services doivent appartenir au même projet Coolify pour partager le réseau Docker interne.

---

## 2. Credentials Google à créer dans n8n

### Google Sheets OAuth2
1. n8n → **Credentials → Add Credential → Google Sheets OAuth2 API**
2. Nommer : `Google Sheets OAuth2`
3. Autoriser avec le compte Google propriétaire du Sheets

> **Note :** Le credential est référencé par nom dans le workflow JSON. Si vous changez le nom, mettez à jour le champ `credentials` dans `n8n/workflow_videogen.json`. L'upload Google Drive est géré directement par l'API — aucun credential Google Drive n8n n'est nécessaire.

---

## 3. Importer le workflow

1. Dans n8n → **Workflows → Import**
2. Coller le contenu de `n8n/workflow_videogen.json`
3. Cliquer **Import**
4. Le workflow s'ouvre avec tous les nœuds

---

## 4. Structure du workflow

```
[Sheets Trigger]       ←── Poll toutes les minutes, détecte Statut=OK
       ↓
[Filter status=OK]     ←── Filtre strictement les lignes avec Statut=OK
       ↓
[Update "En cours"]    ←── Met à jour Sheets: Statut="En cours"
       ↓
[POST /generate]       ←── Appel FastAPI async (retourne 202 + job_id)

─ ─ ─ ─ ─ (callback asynchrone depuis l'API) ─ ─ ─ ─ ─

[Webhook Callback]     ←── L'API rappelle n8n quand le job est terminé
       ↓
[Check type]           ←── "success" → Livré | "blocking_error" / autres → Erreur
       ↓                              ↓
[Update "Livré"]  [Update "Erreur"]
←── Sheets: Statut="Livré" + Lien output=drive_url (fourni par l'API, déjà uploadé sur Drive)
```

---

## 5. Format du Google Sheet

La feuille doit s'appeler **`Campagnes`** avec ces colonnes (ordre exact) :

| Col | Nom | Type | Exemple |
|-----|-----|------|---------|
| A | Script | Texte | `Découvrez notre nouveau produit...` |
| B | Statut | Texte | `OK` → déclenche le pipeline |
| C | Format | Texte | `vertical` ou `horizontal` |
| D | Stratégie | Texte | `A` (Kling pur) ou `B` (Library→Pexels→Kling) |
| E | Durée cible | Nombre | `30`, `60`, `90` (secondes) |
| F | Voix | Texte | ID ElevenLabs (ex: `21m00Tcm4TlvDq8ikWAM`) |
| G | Musique | URL | URL MP3 optionnelle |
| H | CTA | Texte | `Contactez-nous maintenant` |
| I | Lien output | URL | Rempli automatiquement par n8n |
| J | Statut détail | Texte | Rempli automatiquement |

> **Important :** Le champ `row_id` est généré automatiquement par le Sheets Trigger (ligne 1 = row_id 1). Si vous voulez un ID personnalisé, ajoutez une colonne `row_id` et adaptez le mapping dans le nœud `POST /generate`.

---

## 6. Activer le workflow

1. Ouvrir le workflow importé dans n8n
2. Cliquer **Active** (toggle en haut à droite)
3. S'assurer que le **Webhook Callback** est aussi actif (il écoute sur `/webhook/videogen-callback`)

---

## 6b. Déploiement sur Coolify

### Prérequis
- Repository GitHub pushé avec `Dockerfile` (voir `docs/deployment.md`)
- Coolify installé sur le VPS avec n8n déjà déployé dans le même projet

### Étapes dans Coolify

1. **Coolify → New Resource → Application**
2. **Source :** GitHub → sélectionner le repo, branche `main`
3. **Build Pack :** Dockerfile (auto-détecté)
4. **Ports :** `8000` → cocher **Private** (interne uniquement, ne pas exposer publiquement)
5. **Service Name :** noter ce nom (ex: `videogen-api`) — c'est le DNS interne
6. **Environment Variables :** ajouter toutes les variables depuis `.env.example` :

| Variable | Valeur |
|---|---|
| `ENVIRONMENT` | `production` |
| `WORKERS` | `1` |
| `API_SECRET_KEY` | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ANTHROPIC_API_KEY` | `sk-ant-...` |
| `ELEVENLABS_API_KEY` | `...` |
| `KLING_ACCESS_KEY` | `...` |
| `KLING_SECRET_KEY` | `...` |
| `PEXELS_API_KEY` | `...` |
| `CREATOMATE_API_KEY` | `...` |
| `GOOGLE_SERVICE_ACCOUNT_PATH` | `/run/secrets/service_account.json` (voir note ci-dessous) |
| `GOOGLE_DRIVE_FOLDER_ID` | `...` |
| `GOOGLE_SHEETS_ID` | `...` |
| `N8N_WEBHOOK_NOTIFICATION_URL` | `http://<n8n-service-name>:5678/webhook/videogen-callback` |
| `LOGO_URL` | `https://ton-cdn.com/logo.png` |

7. **Deploy** → Coolify build l'image et démarre le container

### Note : Fichier service account Google

Le fichier JSON du compte de service Google doit être accessible dans le container.
La méthode la plus simple avec Coolify : créer un **Volume** pointant vers un fichier sur le VPS.

```bash
# Sur le VPS, placer le fichier JSON :
sudo mkdir -p /opt/videogen
sudo cp service_account.json /opt/videogen/service_account.json

# Dans Coolify → Service → Volumes → Add Volume :
# Source (VPS) : /opt/videogen/service_account.json
# Destination (container) : /run/secrets/service_account.json
# Type : File
```

Puis dans les env vars : `GOOGLE_SERVICE_ACCOUNT_PATH=/run/secrets/service_account.json`

### Réseau interne Docker

Les deux services (n8n et videogen-api) doivent être dans le même **projet** Coolify pour partager le réseau Docker.

- n8n → API : `http://<api-service-name>:8000/generate`
- API → n8n : `http://<n8n-service-name>:5678/webhook/videogen-callback`

Le port 8000 de l'API ne doit **pas** être exposé publiquement.

---

## 7. Premier test

```bash
# 1. Vérifier que l'API est démarrée dans Coolify (Deployments → statut Running)
# 2. Ajouter une ligne de test dans Google Sheets
#    - Script: "Test pipeline. Produit innovant révolutionne le marché."
#    - Statut: OK
#    - Format: vertical
#    - Stratégie: A
#    - Durée cible: 30
#    - Voix: <votre_voice_id_elevenlabs>
#    - CTA: Découvrez-le maintenant

# 3. Attendre 1 minute (poll interval) ou déclencher manuellement dans n8n
# 4. Vérifier dans n8n : Executions → voir le run du pipeline
# 5. Vérifier dans Sheets : Statut = "En cours" puis "Livré"
# 6. Vérifier dans Drive : fichier MP4 présent (uploadé par l'API)
```

---

## 8. Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| Trigger ne se déclenche pas | Credentials Google invalides | Re-autoriser OAuth2 dans n8n |
| POST /generate retourne 401 | `VIDEOGEN_API_SECRET` incorrect | Vérifier la variable n8n + Coolify env vars API |
| Webhook Callback pas reçu | URL n8n non accessible depuis le VPS | Vérifier `N8N_WEBHOOK_URL` + réseau Docker interne Coolify |
| Statut reste "En cours" | Job en timeout ou erreur API externe | Vérifier logs API : Coolify → Service → Logs |
| Drive upload échoue | Dossier Drive ID incorrect ou service account invalide | Vérifier `GOOGLE_DRIVE_FOLDER_ID` + volume service account |

---

## 9. Coûts estimés par pub

| Stratégie | Coût moyen | Détail |
|---|---|---|
| **A** (Kling pur) | ~6–14 $/pub | Kling génère tous les clips |
| **B** (Library→Pexels→Kling) | ~2.3–2.5 $/pub (mois 2+) | Clips réutilisés depuis la bibliothèque |
