# RECAP SESSION — 2026-03-16
## VideoGen API — État complet du projet

---

## 1. CE QUI A ÉTÉ IMPLÉMENTÉ (cette session)

### Feature : Claude Enrichment + Page Review

#### Fichiers modifiés / créés :

| Fichier | Statut | Description |
|---------|--------|-------------|
| `app/models.py` | ✅ modifié | Ajout `persona`, `ambiance` sur `SheetsRow` ; `review_url`, `parent_job_id`, `relaunch_count` sur `VideoJob` ; `review_url` sur `NotificationPayload` ; `source: "review"` sur `ScriptAnalysis` |
| `app/claude.py` | ✅ modifié | Injection `_PERSONA_BLOCK` et `_AMBIANCE_BLOCK` dans le system prompt si fournis |
| `app/main.py` | ✅ modifié | Bypass Claude si `job.script_analysis is not None` (relaunch) ; génération `review_url` après analyse ; passage `persona/ambiance` à `analyze_script()` |
| `app/review.py` | ✅ créé | `GET /review/{job_id}` (page HTML) + `POST /review/{job_id}/relaunch?token=<hmac>` |
| `app/review_html.py` | ✅ créé | Templates HTML : page d'attente (auto-refresh 3s) + page review complète avec textareas éditables |
| `tests/test_review.py` | ✅ créé | 7 tests : page HTML, 404, waiting, relaunch 201, token invalide 403, max count 429, sections vides 422 |
| `tests/test_models_persona.py` | ✅ créé | 7 tests persona/ambiance sur SheetsRow |
| `tests/test_models_review.py` | ✅ créé | 6 tests champs review sur VideoJob/NotificationPayload |
| `tests/test_claude_persona.py` | ✅ créé | 3 tests injection persona/ambiance dans system prompt |

#### Résultats tests : **71/73 ✅** (2 failures pré-existantes non liées)

---

## 2. WORKFLOWS n8n — ÉTAT FINAL

### LANCEMENT TACHES v2
- **Fichier local :** `C:\Users\tobid\Downloads\LANCEMENT TACHES v2 (1).json`
- **Fichier repo :** `docs/n8n-workflow-v2.json`
- **Modification :** Ajout `persona` et `ambiance` dans le body du HTTP Request vers l'API
  ```
  persona: $('Filtre Statut OK').item.json['Personnage'] || '',
  ambiance: $('Filtre Statut OK').item.json['Ambiance'] || ''
  ```
- **À réimporter dans n8n** ✅

### FINALISATION
- **Fichier local :** `C:\Users\tobid\Downloads\FINALISATION.json` ← **À METTRE À JOUR** (voir section 3)
- **Fichier repo :** `docs/n8n-workflow-finalisation.json` ✅ commité

---

## 3. BUGS CORRIGÉS DANS FINALISATION.json

Le fichier `docs/n8n-workflow-finalisation.json` contient les corrections suivantes vs l'original :

| Bug | Avant | Après |
|-----|-------|-------|
| Webhook path | `videogen-callback` | `videogen-result` |
| matchingColumns | `row_id` | `row_number` |
| row_number value | `0` (hardcodé) | `={{ $json['row_number'] }}` |
| drive_url expression | `$('Webhook Callback').item.json.body.drive_url` | `={{ $json['drive_url'] \|\| '' }}` |
| Lien review | absent | `={{ $json['review_url'] \|\| '' }}` |
| Statut detail | absent dans succès | `={{ $json['message'] \|\| '' }}` |
| active | `false` | `true` |

**⚠️ ACTION REQUISE :** Copier `docs/n8n-workflow-finalisation.json` → remplacer `C:\Users\tobid\Downloads\FINALISATION.json` puis réimporter dans n8n.

---

## 4. GOOGLE SHEET — COLONNES REQUISES

| Col | Nom | Rôle |
|-----|-----|------|
| A | Script | Texte voix-off de la pub |
| B | Statut | `OK` déclenche le pipeline |
| C | Format | `9:16`, `16:9`, `1:1` |
| D | Stratégie | `A` (Kling pur) ou `B` (Library→Pexels→Kling) |
| E | Durée | En secondes |
| F | Voix | ID voix ElevenLabs |
| G | Musique | URL fichier musique |
| H | CTA | Texte call-to-action |
| I | Lien output | Rempli auto par FINALISATION |
| J | Statut détail | Rempli auto par FINALISATION |
| K | **Personnage** | Ex: "Femme 30 ans, peau dorée, cheveux noirs" |
| L | **Ambiance** | Ex: "Lumière naturelle dorée, palette chaude" |
| M | **Lien review** | Rempli auto — URL page review `/review/{job_id}` |

---

## 5. ARCHITECTURE PIPELINE

```
Google Sheets (Statut=OK)
    ↓
n8n LANCEMENT TACHES
    ↓ POST /generate
FastAPI (app/main.py)
    ├─ bypass si relaunch (script_analysis déjà fourni)
    ├─ detect_preformatted() → parser
    └─ Claude analyze_script(persona, ambiance) → prompts enrichis
    ↓
ElevenLabs → voix-off MP3
    ↓
Kling AI / Pexels / Library → plans vidéo B-roll
    ↓
Creatomate → assemblage final
    ↓
Google Drive → upload
    ↓
n8n FINALISATION (webhook POST /webhook/videogen-result)
    ↓
Google Sheets (colonnes I, J, M mises à jour)
```

---

## 6. PAGE REVIEW

- **URL :** `{API_BASE_URL}/review/{job_id}`
- **Fonctionnement :** Affiche les prompts générés par Claude ; client peut modifier ; relaunch crée un nouveau job (max 2 relaunches)
- **Sécurité :** HMAC-SHA256 token pour le relaunch
- **Non-bloquant :** Le pipeline ne s'arrête jamais ; review = option post-génération
- **Accès :** Le lien est envoyé dans le webhook n8n (`review_url`) ET écrit dans le Sheet (colonne M)

---

## 7. ÉTAT GIT

```
Branch: master
Remote: https://github.com/tobiags/video-api-n8n.git
Dernier commit: a875ff2 — chore: add corrected FINALISATION n8n workflow
Statut: up to date avec origin/master ✅
```

---

## 8. CHECKLIST DÉPLOIEMENT VPS

- [ ] `git pull` sur le VPS
- [ ] `sudo systemctl restart video-api` (ou équivalent)
- [ ] Réimporter **LANCEMENT TACHES v2 (1).json** dans n8n
- [ ] Copier `docs/n8n-workflow-finalisation.json` → `FINALISATION.json` et réimporter dans n8n
- [ ] Vérifier que les colonnes K (Personnage), L (Ambiance), M (Lien review) existent dans le Sheet
- [ ] Tester avec une ligne Statut=OK

---

## 9. SCRIPT VIDÉO DÉMO (screen recording)

Script complet rédigé pour une vidéo de démo commerciale (~2min30).
**Séquence des fenêtres :**
1. n8n LANCEMENT TACHES — montrer le workflow + une exécution réussie
2. Google Sheet — scroller toutes les colonnes, zoomer Script + Personnage/Ambiance + Statut=OK
3. n8n FINALISATION — montrer l'exécution webhook reçu
4. Google Sheet — montrer colonnes I/J/M remplies automatiquement
5. Google Drive — ouvrir le fichier vidéo livré
6. Lecteur vidéo — jouer la vidéo ~20s
7. Retour Sheet — zoomer colonne Script pour prouver correspondance script↔vidéo
8. CTA — vue d'ensemble n8n canvas

**Message clé :** *"Je construis des Systèmes d'Intelligence Opérationnelle avec n8n & l'IA"*

---

## 10. DETTE TECHNIQUE CONNUE (à traiter plus tard)

| Item | Description |
|------|-------------|
| Redis | Remplacer in-memory store `app.state.jobs` — obligatoire pour multi-workers |
| asyncio.timeout global | Timeout global pipeline Jour 3 |
| 2 tests failing | `test_sheets_row_invalid_duration` + `test_creatomate` — pré-existants, non liés à cette session |
| WORKERS=1 | Garder à 1 jusqu'à Redis intégré |
