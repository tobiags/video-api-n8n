# Design — Mode Script Pré-découpé (script_parser.py)

**Date** : 2026-03-12
**Statut** : Approuvé
**Contexte** : Le client (Théo) écrit ses scripts avec Claude en incluant le découpage scène par scène et les prompts Kling. Le système doit utiliser ses prompts tels quels au lieu de les réinterpréter via l'API Claude.

---

## Problème

Le pipeline actuel envoie systématiquement le script brut à Claude pour générer les `broll_prompt` Kling. Quand le client fournit ses propres prompts scène par scène, Claude les réinterprète et produit des b-rolls incohérents (ex: maman qui parle du travail → homme dans un marché).

## Solution retenue — Approche B : Nouveau module `script_parser.py`

Un module dédié qui détecte automatiquement les scripts pré-découpés et les parse en `ScriptAnalysis` sans appeler l'API Claude.

### Architecture

```
Google Sheets (script) → main.py
                           ├─ detect_preformatted() → True  → parse_preformatted() → ScriptAnalysis
                           └─ detect_preformatted() → False → analyze_script() (claude.py) → ScriptAnalysis
                         ↓
                    ElevenLabs → Kling → Creatomate → Drive
```

Le reste du pipeline ne change pas : il reçoit un `ScriptAnalysis` identique quelle que soit la source.

---

## Section 1 — Module `script_parser.py`

### Format détecté

```
PLAN \d+ \((\d+)[–-](\d+)s\) [—–-]+ .*
🎙 "(.+)"
🎬 (.+)
```

Le pattern accepte les variantes de tirets : hyphen `-`, en-dash `–`, em-dash `—` (copier-coller depuis différents éditeurs). Le seuil de détection est **≥ 2 blocs** pour éviter les faux positifs sur un script qui contiendrait le mot "PLAN" une seule fois.

Exemple réel du client :
```
PLAN 1 (0-5s) — HOOK
🎙 "Un documentaire gratuit a changé la vie de cet homme."
🎬 Close-up portrait of a rugged French man in his 40s with stubble...
```

### API publique

```python
def detect_preformatted(script: str) -> bool:
    """Retourne True si au moins 2 blocs PLAN avec 🎙 + 🎬 sont trouvés."""

def parse_preformatted(script: str, format_: VideoFormat) -> ScriptAnalysis:
    """Parse le script pré-découpé en ScriptAnalysis (synchrone, pas d'I/O).

    Note: fonction synchrone par design (pure CPU, pas d'appel réseau).
    Le caller ne doit PAS l'awaiter.

    total_duration est calculé comme sum(section.duration for section in sections),
    dérivé des timestamps parsés (pas de row.duration).

    Raises:
        ScriptParserError: si le format est malformé.
    """
```

### Mapping des champs

| Champ `ScriptSection` | Source dans le script |
|---|---|
| `id` | Numéro du plan (1-indexed) |
| `text` | Contenu après 🎙 (entre guillemets) |
| `broll_prompt` | Contenu après 🎬 (prompt Kling tel quel) |
| `start` | Premier nombre dans `(Xs-Ys)` |
| `end` | Second nombre dans `(Xs-Ys)` |
| `duration` | `end - start` |
| `keywords` | Jusqu'à 3 mots-clés anglais extraits du prompt (voir Section 3) |
| `scene_type` | Inféré du label complet après le tiret, case-insensitive (voir Section 3) |

### Champs dérivés

- `total_duration` = `sum(section.duration for section in sections)` — calculé depuis les timestamps parsés, pas depuis `row.duration`
- `source` (optionnel) = `"parser"` — champ ajouté à `ScriptAnalysis` pour traçabilité (`Literal["claude", "parser"]`, défaut `"claude"`)

### Validation

Utilise le modèle Pydantic `ScriptAnalysis` existant. Le validator `validate_total_duration` s'applique automatiquement (sum des durées == total_duration).

Validations supplémentaires dans le parser :
- Timestamps non-contigus (gap > 0s entre plans) → `ScriptParserError` avec message
- Timestamps qui se chevauchent → `ScriptParserError` avec message
- Contenu vide après 🎙 ou 🎬 (marker présent mais texte vide/whitespace) → `ScriptParserError`

### Erreurs

`ScriptParserError(VideoGenException)` avec messages explicites en français :
- `"Plan 3 : marqueur 🎙 manquant"`
- `"Plan 5 : timestamps invalides (end <= start)"`
- `"Plan 3 : prompt Kling vide après 🎬"`
- `"Plans 2-3 : timestamps non-contigus (gap de 2s)"`

---

## Section 2 — Routage dans `main.py`

Changement minimal dans `_run_pipeline`, avant l'appel à `analyze_script()` :

```python
from app.script_parser import detect_preformatted, parse_preformatted

# Stage 1 : Analyse du script
if detect_preformatted(row.script):
    logger.info("Script pré-découpé détecté, bypass Claude")
    script_analysis = parse_preformatted(row.script, row.format)  # sync, pas d'await
    # Skip Claude stage, passe direct à ElevenLabs
else:
    script_analysis = await analyze_script(...)  # async, appel API Claude
```

**Impacts** :
- Script pré-découpé : 0 token Claude, 0 latence supplémentaire
- Script normal : comportement identique à aujourd'hui
- Progression : passe de 0% à 25% directement (skip étape Claude 10%)

**Aucun changement en aval** : ElevenLabs, Kling, Creatomate, n8n reçoivent le même `ScriptAnalysis`.

---

## Section 3 — Extraction keywords et scene_type

### Keywords (pour fallback Pexels)

Extraction simple sans IA :
1. Tokenize le `broll_prompt` : split sur whitespace + ponctuation, puis lowercase
2. Split les mots composés avec tiret (`Close-up` → `close`, `up`)
3. Filtre stop words anglais (`a, the, of, in, with, and, at, his, her, etc.`)
4. Filtre adjectifs cinéma récurrents (`cinematic, dramatic, vertical, format, shallow, depth, field, warm, cold, slow, motion, etc.`)
5. Prend **jusqu'à 3** premiers mots significatifs restants (si < 3 disponibles, retourne ce qu'il y a)

Exemple : `"Close-up portrait of a rugged French man in his 40s with stubble, arms crossed"` → `["portrait", "rugged", "man"]`

### Scene_type — mapping du label

Le label est extrait comme la chaîne complète après le tiret (em-dash/en-dash/hyphen), strippée et comparée en **uppercase**. Le matching est sur le label complet (ex: `"SOCIAL PROOF"` est un seul label, pas deux mots séparés).

| Label (case-insensitive, trimmed) | `scene_type` |
|---|---|
| HOOK | `emotion` |
| AVANT, DOULEUR, FRUSTRATION | `emotion` |
| DÉCOUVERTE, MÉCANISME | `ambient` |
| TRANSFORMATION, RÉSULTAT | `testimonial` |
| SOCIAL PROOF | `testimonial` |
| CTA | `cta` |
| *(tout autre label)* | `ambient` |

---

## Section 4 — Tests

Fichier : `tests/test_script_parser.py`

| # | Test | Vérifie |
|---|---|---|
| 1 | `test_detect_preformatted_valid` | Script 9 plans → `True` |
| 2 | `test_detect_preformatted_normal_script` | Script brut → `False` |
| 3 | `test_detect_preformatted_partial` | 1 seul PLAN → `False` |
| 4 | `test_parse_preformatted_full` | 9 sections avec id, text, broll_prompt, start, end, duration |
| 5 | `test_parse_preformatted_keywords` | Keywords extraits et en anglais |
| 6 | `test_parse_preformatted_scene_types` | Mapping HOOK→emotion, CTA→cta |
| 7 | `test_parse_preformatted_validation` | `ScriptAnalysis` Pydantic valide |
| 8 | `test_parse_malformed_missing_voice` | Plan sans 🎙 → `ScriptParserError` |
| 9 | `test_parse_malformed_missing_prompt` | Plan sans 🎬 → `ScriptParserError` |
| 10 | `test_parse_malformed_timestamps` | Timestamps inversés → `ScriptParserError` |
| 11 | `test_parse_empty_prompt_after_marker` | 🎬 suivi de whitespace → `ScriptParserError` |
| 12 | `test_parse_non_contiguous_timestamps` | Gap entre plans → `ScriptParserError` |
| 13 | `test_parse_overlapping_timestamps` | Chevauchement → `ScriptParserError` |
| 14 | `test_parse_dash_variants` | Fonctionne avec `-`, `–`, `—` |
| 15 | `test_pipeline_routing_preformatted` | `_run_pipeline` skip Claude si pré-découpé (mock downstream) |
| 16 | `test_pipeline_routing_normal` | `_run_pipeline` appelle Claude si script normal (mock downstream) |

---

## Hors scope

- Batch upload (30 scripts) — feature séparée, pas dans ce spec
- Endpoint API dédié `/generate-from-plans` — non retenu, Google Sheets uniquement
- HeyGen — non retenu, ElevenLabs conservé pour les voix
- Catalogue de voix dans le dashboard — feature séparée
