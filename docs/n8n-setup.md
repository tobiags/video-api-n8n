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
| `VIDEOGEN_API_URL` | `https://api.mondomaine.com` | URL de l'API VideoGen (sans slash final) |
| `VIDEOGEN_API_SECRET` | `votre-clé-secrète` | Valeur de `API_SECRET_KEY` dans `.env` |
| `N8N_WEBHOOK_URL` | `https://n8n.mondomaine.com` | URL publique de votre instance n8n |

---

## 2. Credentials Google à créer dans n8n

### Google Sheets OAuth2
1. n8n → **Credentials → Add Credential → Google Sheets OAuth2 API**
2. Nommer : `Google Sheets OAuth2`
3. Autoriser avec le compte Google propriétaire du Sheets

### Google Drive OAuth2
1. n8n → **Credentials → Add Credential → Google Drive OAuth2 API**
2. Nommer : `Google Drive OAuth2`
3. Autoriser avec le même compte Google

> **Note :** Les credentials sont référencés par nom dans le workflow JSON. Si vous changez le nom, mettez à jour les champs `credentials` dans `n8n/workflow_videogen.json`.

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
[Check type]           ←── "completed" → Drive | "blocking_error" → Erreur
       ↓                              ↓
[Upload Drive]    [Update "Erreur"]
       ↓
[Update "Livré"]       ←── Sheets: Statut="Livré" + Lien output=URL Drive
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

## 7. Premier test

```bash
# 1. Démarrer l'API en local (ou vérifier qu'elle est déployée)
make dev

# 2. Ajouter une ligne de test dans Google Sheets
#    - Script: "Test pipeline. Produit innovant révolutionne le marché."
#    - Statut: OK
#    - Format: vertical
#    - Stratégie: A
#    - Durée: 30
#    - Voix: <votre_voice_id_elevenlabs>
#    - CTA: Découvrez-le maintenant

# 3. Attendre 1 minute (poll interval) ou déclencher manuellement dans n8n
# 4. Vérifier dans n8n : Executions → voir le run du pipeline
# 5. Vérifier dans Sheets : Statut = "En cours" puis "Livré"
# 6. Vérifier dans Drive : fichier MP4 présent
```

---

## 8. Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| Trigger ne se déclenche pas | Credentials Google invalides | Re-autoriser OAuth2 dans n8n |
| POST /generate retourne 401 | `VIDEOGEN_API_SECRET` incorrect | Vérifier la variable n8n + `.env` API |
| Webhook Callback pas reçu | URL n8n non accessible depuis le VPS | Vérifier `N8N_WEBHOOK_URL` + firewall |
| Statut reste "En cours" | Job en timeout ou erreur API externe | Vérifier logs API : `journalctl -u videogen -f` |
| Drive upload échoue | Dossier Drive ID incorrect | Vérifier `GOOGLE_DRIVE_FOLDER_ID` |

---

## 9. Coûts estimés par pub

| Stratégie | Coût moyen | Détail |
|---|---|---|
| **A** (Kling pur) | ~6–14 $/pub | Kling génère tous les clips |
| **B** (Library→Pexels→Kling) | ~2.3–2.5 $/pub (mois 2+) | Clips réutilisés depuis la bibliothèque |
