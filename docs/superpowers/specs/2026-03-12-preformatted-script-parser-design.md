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
PLAN \d+ \((\d+)-(\d+)s\) — .*
🎙 "(.+)"
🎬 (.+)
```

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
    """Parse le script pré-découpé en ScriptAnalysis.

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
| `keywords` | 3 mots-clés anglais extraits du prompt (voir Section 3) |
| `scene_type` | Inféré du label après le tiret (voir Section 3) |

### Validation

Utilise le modèle Pydantic `ScriptAnalysis` existant. Le validator `validate_total_duration` s'applique automatiquement (sum des durées == total_duration).

### Erreurs

`ScriptParserError(PipelineError)` avec messages explicites en français :
- `"Plan 3 : marqueur 🎙 manquant"`
- `"Plan 5 : timestamps invalides (end <= start)"`

---

## Section 2 — Routage dans `main.py`

Changement minimal dans `_run_pipeline`, avant l'appel à `analyze_script()` :

```python
from app.script_parser import detect_preformatted, parse_preformatted

# Stage 1 : Analyse du script
if detect_preformatted(row.script):
    script_analysis = parse_preformatted(row.script, row.format)
    # Skip Claude stage, passe direct à ElevenLabs
else:
    script_analysis = await analyze_script(...)
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
1. Tokenize le `broll_prompt`
2. Filtre stop words anglais (`a, the, of, in, with, and, at, etc.`)
3. Filtre adjectifs cinéma récurrents (`cinematic, dramatic, vertical, format, shallow, depth, field, etc.`)
4. Prend les 3 premiers mots significatifs

Exemple : `"Close-up portrait of a rugged French man..."` → `["portrait", "man", "industrial"]`

### Scene_type — mapping du label

| Label | `scene_type` |
|---|---|
| HOOK | `emotion` |
| AVANT, DOULEUR, FRUSTRATION | `emotion` |
| DÉCOUVERTE, MÉCANISME | `ambient` |
| TRANSFORMATION, RÉSULTAT | `testimonial` |
| SOCIAL PROOF | `testimonial` |
| CTA | `cta` |
| *(autre)* | `ambient` |

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
| 11 | `test_pipeline_routing_preformatted` | `_run_pipeline` skip Claude si pré-découpé |
| 12 | `test_pipeline_routing_normal` | `_run_pipeline` appelle Claude si script normal |

---

## Hors scope

- Batch upload (30 scripts) — feature séparée, pas dans ce spec
- Endpoint API dédié `/generate-from-plans` — non retenu, Google Sheets uniquement
- HeyGen — non retenu, ElevenLabs conservé pour les voix
- Catalogue de voix dans le dashboard — feature séparée
