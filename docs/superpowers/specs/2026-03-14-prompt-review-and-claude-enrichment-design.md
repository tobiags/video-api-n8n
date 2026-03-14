# Design Spec: Enrichissement Claude + Page Review Prompts

**Date:** 2026-03-14
**Statut:** Approuvé
**Scope:** Améliorer la qualité des prompts Kling générés par Claude + donner au client un outil de contrôle optionnel pour visualiser/modifier les prompts.

---

## 1. Contexte et problème

Claude génère des prompts Kling qui ne correspondent pas toujours au script :
- Script d'une maman → Claude génère un homme dans un marché
- Le genre/sexe du protagoniste n'est pas respecté
- L'ambiance visuelle est incohérente avec le ton du script

**Deux axes de solution :**
1. Enrichir le prompt Claude avec le contexte personnage/ambiance
2. Offrir une page de review optionnelle pour que le client puisse vérifier et modifier les prompts

---

## 2. Volet 1 : Enrichissement du prompt Claude

### 2.1 Nouvelles colonnes Google Sheet

| Colonne | Position | Obligatoire | Exemple |
|---------|----------|-------------|---------|
| `Personnage` | K (après Statut detail) | Non | `femme 30 ans, mère de famille, fatiguée` |
| `Ambiance` | L | Non | `cinématique chaud, lumière dorée` |

### 2.2 Modifications `models.py` — SheetsRow

Deux nouveaux champs optionnels :

```python
persona: str | None = Field(None, description="Description du protagoniste visuel (genre, âge, apparence)")
ambiance: str | None = Field(None, description="Style visuel souhaité (tonalité, lumière, palette)")
```

Avec le même `strip_sheets_strings` validator appliqué.

### 2.3 Modifications `claude.py` — System prompt

Ajouter un bloc conditionnel dans `_SYSTEM_PROMPT` :

```
CONTEXTE PERSONNAGE (OBLIGATOIRE si fourni) :
{persona}
→ Utilise EXACTEMENT ce profil pour CHAQUE prompt Kling : genre, âge, apparence.
→ Si aucun personnage n'est fourni, DÉDUIS-LE du script (accords grammaticaux,
  contexte, métier) et applique-le de façon cohérente à TOUTES les scènes.

AMBIANCE VISUELLE (si fournie) :
{ambiance}
→ Applique ce style visuel à tous les plans : tonalité, lumière, palette.
```

Si `persona` est None, le bloc personnage indique à Claude de déduire du script.
Si `ambiance` est None, le bloc ambiance est omis du prompt.

### 2.4 Modifications `claude.py` — Signature `analyze_script()`

Ajouter paramètres :
```python
async def analyze_script(
    script: str,
    format_: VideoFormat,
    duration: int,
    aspect_ratio: str,
    http_client: httpx.AsyncClient,
    settings: Settings,
    persona: str | None = None,    # NOUVEAU
    ambiance: str | None = None,   # NOUVEAU
) -> ScriptAnalysis:
```

### 2.5 Modifications `main.py` — Appel analyze_script

Passer `row.persona` et `row.ambiance` à `analyze_script()`.

### 2.6 Modifications workflow n8n

POST body ajoute :
```
persona: $json['Personnage'] || ''
ambiance: $json['Ambiance'] || ''
```

---

## 3. Volet 2 : Page de review optionnelle

### 3.1 Principe fondamental

**Le pipeline ne s'arrête JAMAIS.** La page review est un outil de contrôle optionnel, pas un gate.

### 3.2 Trois scénarios

| Scénario | Comportement |
|----------|-------------|
| Client ne clique pas | Pipeline automatique complet, comme avant |
| Client ouvre le lien pendant le pipeline | Visualisation en lecture seule, pipeline continue |
| Client modifie et clique "Relancer" | Nouveau job créé avec prompts modifiés (bypass Claude) |

### 3.3 Pourquoi un nouveau job

- Pas d'interruption du pipeline en cours (complexe et fragile)
- Le client peut comparer les deux résultats
- Simple à implémenter : POST /review/{id}/relaunch crée un VideoGenerationRequest avec les prompts modifiés

### 3.4 Endpoint GET /review/{job_id}

**URL :** `GET /review/{job_id}`
**Auth :** Aucune — le job_id UUID v4 est suffisamment imprévisible
**Disponible :** Dès que `job.script_analysis` est rempli (après étape Claude ou parser)

**Page HTML avec :**
- Titre : "Review des prompts — Job {job_id_court}"
- Script original (lecture seule, collapsible)
- Pour chaque section/scène :
  - Numéro de plan + timecodes (lecture seule)
  - Texte voix off (lecture seule)
  - **Prompt Kling** (textarea éditable, pré-rempli)
  - **Keywords** (input éditable, pré-rempli)
  - Scene type (select éditable)
- Statut du pipeline en temps réel (badge : en cours / terminé / échoué)
- Bouton **"Relancer avec mes modifications"** (visible seulement si des champs ont été modifiés)
- Lien vers la vidéo finale si le job est terminé

**Style :** Simple, responsive, même charte que le monitor existant.

### 3.5 Endpoint POST /review/{job_id}/relaunch

**Auth :** Aucune (même logique UUID)
**Body :**
```json
{
  "sections": [
    {
      "id": 1,
      "broll_prompt": "prompt modifié par le client",
      "keywords": ["mot1", "mot2"],
      "scene_type": "emotion"
    }
  ]
}
```

**Comportement :**
1. Récupère le job original
2. Crée un nouveau `VideoGenerationRequest` avec les mêmes paramètres (script, format, voix, etc.)
3. Construit un `ScriptAnalysis` avec `source="review"` en utilisant les sections du job original mais avec les prompts/keywords/scene_type modifiés
4. Lance un nouveau pipeline à partir de l'étape ElevenLabs (bypass Claude)
5. Retourne le nouveau `job_id` + redirect vers la page review du nouveau job

### 3.6 Nouveau `source` literal

Ajouter `"review"` aux valeurs possibles de `ScriptAnalysis.source` :
```python
source: Literal["claude", "parser", "review"]
```

### 3.7 Lien review dans le pipeline

Après l'étape Claude/parser dans `run_pipeline`, écrire le review_url dans `job.review_url` :
```python
review_url = f"{settings.API_BASE_URL}/review/{job_id}"
```

Ce lien est inclus dans le webhook de notification n8n (champ `review_url` dans `NotificationPayload`), et n8n l'écrit dans la colonne `Statut detail` du Sheet.

### 3.8 Modifications NotificationPayload

Ajouter champ optionnel :
```python
review_url: str | None = Field(None, description="URL de la page review des prompts")
```

---

## 4. Fichiers impactés

| Fichier | Modifications |
|---------|--------------|
| `app/models.py` | SheetsRow +persona/ambiance, ScriptAnalysis source +review, NotificationPayload +review_url, VideoJob +review_url |
| `app/claude.py` | System prompt enrichi, signature +persona/ambiance |
| `app/main.py` | Passer persona/ambiance à analyze_script, générer review_url, inclure dans notification |
| `app/review.py` | **NOUVEAU** — Page HTML review + endpoint POST relaunch |
| `app/errors.py` | ReviewError si job non trouvé ou pas de script_analysis |
| `tests/test_claude.py` | Tests prompt enrichi avec persona/ambiance |
| `tests/test_review.py` | **NOUVEAU** — Tests page review + relaunch |
| Workflow n8n | POST body +persona/ambiance, webhook handler pour review_url → Statut detail |
| Google Sheet | Colonnes K (Personnage) et L (Ambiance) |

---

## 5. Ce qui ne change PAS

- Le pipeline existant reste identique si persona/ambiance sont vides
- Les scripts pré-formatés (PLAN/🎙/🎬) ne passent pas par Claude → la review montre les prompts du parser
- La page monitor existante n'est pas modifiée
- Pas de nouvelle dépendance Python
