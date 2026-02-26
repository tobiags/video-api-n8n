# VideoGen API — Jour 2-4 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Implémenter les 5 modules métier (claude, elevenlabs, kling, library, creatomate), les tests d'intégration bout-en-bout, le workflow n8n, et le déploiement VPS systemd.

**Architecture:** Pipeline orchestré par `main.py` → `claude.py` → `elevenlabs.py` → `kling.py` ou `library.py` → `creatomate.py`. Chaque module reçoit le `httpx.AsyncClient` partagé comme paramètre, ce qui le rend mockable dans les tests sans patcher de globals. Les retry/timeout sont gérés dans chaque module, pas dans l'orchestrateur.

**Tech Stack:** `anthropic` SDK 0.50, `httpx` 0.28 (mock via `AsyncMock`), `PyJWT` 2.10, `asyncio.Semaphore` pour Kling, `google-api-python-client` pour Drive/Sheets.

**Répertoire de travail:** `C:\Users\tobid\Downloads\CLAUDE\video-api\`

**Lancer les tests:** `python -m pytest tests/ -v --tb=short`

---

## KNOWN DEBT (à garder en tête)

Issues identifiées par code review, à gérer pendant l'implémentation :

- **C1** — `drive_url` dans VideoJob = URL Creatomate, pas Drive. Renommer en `video_url` si n8n upload Drive séparé.
- **C4** — `VideoJob` est un `BaseModel` muté directement. Acceptable jusqu'à Redis (Jour 2 fin).
- **I2** — Pas de timeout global pipeline. Wrapper `run_pipeline` avec `asyncio.timeout` au Task 6.
- **I3** — `voice_id` sans fallback vers `ELEVENLABS_DEFAULT_VOICE_ID`. Gérer au Task 2.
- **I4** — `CreatomateRenderRequest` bypassé dans `assemble_video`. À utiliser au Task 5.

---

## Task 1 — `claude.py` : Découpage script + prompts B-roll

**PRD §4.1** — Claude découpe le script en N sections ~5s, génère un prompt B-roll par section, valide JSON (somme durées == total_duration). Retry x3 avec contexte d'erreur.

**Files:**
- Modify: `app/claude.py`
- Create: `tests/test_claude.py`

---

### Step 1.1 — Écrire le test : réponse JSON valide

```python
# tests/test_claude.py
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from app.models import ScriptAnalysis, VideoFormat

VALID_CLAUDE_JSON = {
    "total_duration": 10,
    "sections": [
        {"id": 1, "text": "Intro", "start": 0, "end": 5, "duration": 5,
         "broll_prompt": "entrepreneur moderne bureau lumière chaude 9:16",
         "keywords": ["entrepreneur", "bureau"], "scene_type": "emotion"},
        {"id": 2, "text": "CTA", "start": 5, "end": 10, "duration": 5,
         "broll_prompt": "produit gros plan fond blanc épuré 9:16",
         "keywords": ["produit"], "scene_type": "cta"},
    ]
}

MINIMAL_ENV = {
    "API_SECRET_KEY": "test-secret-key-32-chars-minimum!!",
    "ANTHROPIC_API_KEY": "sk-ant-test",
    "ELEVENLABS_API_KEY": "el-test",
    "ELEVENLABS_DEFAULT_VOICE_ID": "voice-id-test",
    "KLING_ACCESS_KEY": "kling-access-test",
    "KLING_SECRET_KEY": "kling-secret-test",
    "PEXELS_API_KEY": "pexels-test",
    "CREATOMATE_API_KEY": "creat-test",
    "CREATOMATE_TEMPLATE_VERTICAL": "tmpl-v",
    "CREATOMATE_TEMPLATE_HORIZONTAL": "tmpl-h",
    "GOOGLE_SERVICE_ACCOUNT_PATH": "/tmp/sa.json",
    "GOOGLE_DRIVE_FOLDER_ID": "drive-id",
    "GOOGLE_SHEETS_ID": "sheets-id",
}

@pytest.fixture
def env_vars(monkeypatch):
    for k, v in MINIMAL_ENV.items():
        monkeypatch.setenv(k, v)

@pytest.mark.asyncio
async def test_analyze_script_returns_valid_analysis(env_vars):
    from app.claude import analyze_script
    from app.config import Settings

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(VALID_CLAUDE_JSON))]

    mock_client_instance = AsyncMock()
    mock_client_instance.messages.create = AsyncMock(return_value=mock_message)

    with patch("app.claude.anthropic.AsyncAnthropic", return_value=mock_client_instance):
        result = await analyze_script(
            script="Vous perdez des heures à créer vos pubs. Notre outil change tout.",
            format_=VideoFormat.VERTICAL,
            duration=10,
            aspect_ratio="9:16",
            http_client=AsyncMock(spec=httpx.AsyncClient),
            settings=Settings(),
        )

    assert isinstance(result, ScriptAnalysis)
    assert result.total_duration == 10
    assert result.section_count == 2
    assert result.sections[0].broll_prompt == "entrepreneur moderne bureau lumière chaude 9:16"
```

### Step 1.2 — Lancer le test, vérifier qu'il échoue

```bash
python -m pytest tests/test_claude.py::test_analyze_script_returns_valid_analysis -v
```
Attendu : **FAIL** — `NotImplementedError: claude.analyze_script`

---

### Step 1.3 — Écrire le test : retry sur JSON invalide

```python
@pytest.mark.asyncio
async def test_analyze_script_retries_on_invalid_json(env_vars):
    from app.claude import analyze_script
    from app.config import Settings
    from app.errors import ClaudeInvalidJSONError

    bad_response = MagicMock()
    bad_response.content = [MagicMock(text="not json at all")]

    mock_client_instance = AsyncMock()
    mock_client_instance.messages.create = AsyncMock(return_value=bad_response)

    with patch("app.claude.anthropic.AsyncAnthropic", return_value=mock_client_instance):
        with pytest.raises(ClaudeInvalidJSONError):
            await analyze_script(
                script="Script test " * 10,
                format_=VideoFormat.VERTICAL,
                duration=10,
                aspect_ratio="9:16",
                http_client=AsyncMock(spec=httpx.AsyncClient),
                settings=Settings(),
            )

    # Doit avoir été appelé CLAUDE_MAX_RETRIES=3 fois
    assert mock_client_instance.messages.create.call_count == 3
```

### Step 1.4 — Implémenter `app/claude.py`

```python
"""
claude.py — Module d'analyse script + génération prompts B-roll (PRD §4.1)
"""
import json
import logging

import anthropic
import httpx

from app.config import Settings
from app.errors import ClaudeAPIError, ClaudeInvalidJSONError
from app.models import ScriptAnalysis, VideoFormat

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """Tu es un expert en publicité vidéo. Ton rôle est de découper un script
publicitaire en sections temporelles et de générer un prompt B-roll Kling pour chaque section.

RÈGLES STRICTES :
1. Chaque section dure exactement {clip_duration} secondes
2. La somme de toutes les durées doit être exactement égale à {total_duration} secondes
3. Chaque broll_prompt doit inclure le ratio {aspect_ratio}, le style visuel, l'action et le cadrage
4. Retourne UNIQUEMENT un objet JSON valide, sans markdown, sans commentaires

SCHÉMA JSON REQUIS :
{{
  "total_duration": <int>,
  "sections": [
    {{
      "id": <int>,
      "text": "<texte narré>",
      "start": <int secondes>,
      "end": <int secondes>,
      "duration": <int secondes>,
      "broll_prompt": "<prompt Kling complet avec ratio {aspect_ratio}>",
      "keywords": ["<mot-clé1>", "<mot-clé2>"],
      "scene_type": "<emotion|product|testimonial|cta|ambient|tutorial>"
    }}
  ]
}}"""

_USER_PROMPT = """Script à découper ({total_duration} secondes, format {aspect_ratio}) :

{script}"""

_RETRY_PROMPT = """Ton JSON précédent était invalide. Erreur : {error}

Reprends l'analyse et retourne UNIQUEMENT un JSON valide respectant strictement le schéma.
La somme des durées DOIT être exactement {total_duration} secondes."""


async def analyze_script(
    script: str,
    format_: VideoFormat,
    duration: int,
    aspect_ratio: str,
    http_client: httpx.AsyncClient,
    settings: Settings,
) -> ScriptAnalysis:
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    messages = [
        {"role": "user", "content": _USER_PROMPT.format(
            total_duration=duration, aspect_ratio=aspect_ratio, script=script
        )}
    ]
    system = _SYSTEM_PROMPT.format(
        clip_duration=settings.KLING_DURATION,
        total_duration=duration,
        aspect_ratio=aspect_ratio,
    )
    last_error: Exception | None = None

    for attempt in range(settings.CLAUDE_MAX_RETRIES):
        try:
            response = await client.messages.create(
                model=settings.CLAUDE_MODEL,
                max_tokens=settings.CLAUDE_MAX_TOKENS,
                system=system,
                messages=messages,
            )
            raw = response.content[0].text.strip()
            # Nettoyer éventuel bloc markdown ```json ... ```
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw)
            analysis = ScriptAnalysis(**data)
            logger.info("Claude OK — %d sections, durée %ds (tentative %d)",
                        analysis.section_count, analysis.total_duration, attempt + 1)
            return analysis

        except (json.JSONDecodeError, Exception) as e:
            last_error = e
            logger.warning("Claude tentative %d/%d échouée : %s",
                           attempt + 1, settings.CLAUDE_MAX_RETRIES, e)
            if attempt < settings.CLAUDE_MAX_RETRIES - 1:
                messages.append({"role": "assistant", "content": raw if 'raw' in locals() else ""})
                messages.append({"role": "user", "content": _RETRY_PROMPT.format(
                    error=str(e), total_duration=duration
                )})

    raise ClaudeInvalidJSONError(
        f"Claude a retourné un JSON invalide après {settings.CLAUDE_MAX_RETRIES} tentatives. "
        f"Dernière erreur : {last_error}"
    )
```

### Step 1.5 — Lancer les tests Claude

```bash
python -m pytest tests/test_claude.py -v
```
Attendu : **2 passed**

### Step 1.6 — Lancer la suite complète

```bash
python -m pytest tests/ -v
```
Attendu : **17 passed** (15 existants + 2 nouveaux)

### Step 1.7 — Commit

```bash
git add app/claude.py tests/test_claude.py
git commit -m "feat: implement claude.py — script analysis with retry on invalid JSON"
```

---

## Task 2 — `elevenlabs.py` : Voix off + timestamps

**PRD §4.2** — Appel ElevenLabs `/text-to-speech/{voice_id}/with-timestamps`, extraction timestamps mot par mot, retry x2 backoff (5s, 10s).

**Files:**
- Modify: `app/elevenlabs.py`
- Create: `tests/test_elevenlabs.py`
- Add dep: `aiofiles` pour écriture async MP3

---

### Step 2.1 — Écrire les tests

```python
# tests/test_elevenlabs.py
import base64
import json
import pytest
from unittest.mock import AsyncMock, MagicMock
import httpx

# Réutiliser MINIMAL_ENV de test_claude.py (ou extraire dans conftest.py)
from tests.test_claude import MINIMAL_ENV

@pytest.fixture
def env_vars(monkeypatch):
    for k, v in MINIMAL_ENV.items():
        monkeypatch.setenv(k, v)

def _fake_audio_b64() -> str:
    return base64.b64encode(b"fake-mp3-data").decode()

def _fake_el_response() -> dict:
    return {
        "audio_base64": _fake_audio_b64(),
        "normalized_alignment": {
            "characters": ["H", "e", "l", "l", "o", " ", "w", "o", "r", "l", "d"],
            "character_start_times_seconds": [0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5],
            "character_end_times_seconds":   [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.6],
        }
    }

@pytest.mark.asyncio
async def test_generate_voiceover_returns_result(env_vars, tmp_path, monkeypatch):
    from app.elevenlabs import generate_voiceover
    from app.config import Settings
    monkeypatch.setenv("LIBRARY_PATH", str(tmp_path / "clips"))
    settings = Settings()

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = _fake_el_response()
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = mock_response

    monkeypatch.setattr("app.elevenlabs.AUDIO_STORAGE_DIR", str(tmp_path))

    result = await generate_voiceover(
        script="Hello world",
        voice_id="voice-123",
        http_client=mock_client,
        settings=settings,
    )

    assert result.voice_id == "voice-123"
    assert result.audio_duration_ms > 0
    assert len(result.timestamps) > 0
    assert result.timestamps[0].word  # au moins un mot
    mock_client.post.assert_called_once()

@pytest.mark.asyncio
async def test_generate_voiceover_retries_on_error(env_vars, tmp_path, monkeypatch):
    from app.elevenlabs import generate_voiceover
    from app.config import Settings
    from app.errors import ElevenLabsAPIError
    monkeypatch.setattr("app.elevenlabs.AUDIO_STORAGE_DIR", str(tmp_path))
    settings = Settings()

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = httpx.HTTPError("Connection failed")

    with pytest.raises(ElevenLabsAPIError):
        await generate_voiceover("Hello", "voice-123", mock_client, settings)

    # ELEVENLABS_MAX_RETRIES=2 → 2 appels total (attempt 0 et 1)
    assert mock_client.post.call_count == 2
```

### Step 2.2 — Vérifier l'échec

```bash
python -m pytest tests/test_elevenlabs.py -v
```
Attendu : **FAIL** — `NotImplementedError`

### Step 2.3 — Implémenter `app/elevenlabs.py`

```python
"""
elevenlabs.py — Module voix off + timestamps (PRD §4.2)
"""
import asyncio
import base64
import logging
import os
import uuid
from pathlib import Path

import httpx

from app.config import Settings
from app.errors import ElevenLabsAPIError, ElevenLabsTimeoutError
from app.models import ElevenLabsResult, WordTimestamp

logger = logging.getLogger(__name__)

# Répertoire de stockage audio sur le VPS (override dans les tests)
AUDIO_STORAGE_DIR = "/opt/videogen/audio"


async def generate_voiceover(
    script: str,
    voice_id: str,
    http_client: httpx.AsyncClient,
    settings: Settings,
) -> ElevenLabsResult:
    last_error: Exception | None = None

    for attempt in range(settings.ELEVENLABS_MAX_RETRIES):
        try:
            response = await http_client.post(
                f"{settings.ELEVENLABS_BASE_URL}/text-to-speech/{voice_id}/with-timestamps",
                headers={"xi-api-key": settings.elevenlabs_api_key, "Content-Type": "application/json"},
                json={
                    "text": script,
                    "model_id": settings.ELEVENLABS_MODEL_ID,
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
                },
                timeout=120.0,
            )
            response.raise_for_status()
            data = response.json()
            return _parse_response(data, voice_id, script)

        except httpx.TimeoutException as e:
            last_error = e
            logger.warning("ElevenLabs timeout tentative %d/%d", attempt + 1, settings.ELEVENLABS_MAX_RETRIES)
        except httpx.HTTPStatusError as e:
            last_error = e
            logger.warning("ElevenLabs HTTP %d tentative %d/%d", e.response.status_code, attempt + 1, settings.ELEVENLABS_MAX_RETRIES)
        except Exception as e:
            last_error = e
            logger.warning("ElevenLabs erreur tentative %d/%d : %s", attempt + 1, settings.ELEVENLABS_MAX_RETRIES, e)

        if attempt < settings.ELEVENLABS_MAX_RETRIES - 1:
            delay = settings.ELEVENLABS_BACKOFF_BASE * (2 ** attempt)  # 5s, 10s
            logger.info("ElevenLabs retry dans %.0fs...", delay)
            await asyncio.sleep(delay)

    if isinstance(last_error, httpx.TimeoutException):
        raise ElevenLabsTimeoutError(f"ElevenLabs timeout après {settings.ELEVENLABS_MAX_RETRIES} tentatives")
    raise ElevenLabsAPIError(f"ElevenLabs échec après {settings.ELEVENLABS_MAX_RETRIES} tentatives : {last_error}")


def _parse_response(data: dict, voice_id: str, script: str) -> ElevenLabsResult:
    audio_bytes = base64.b64decode(data["audio_base64"])
    audio_path = _save_audio(audio_bytes)

    alignment = data.get("normalized_alignment", {})
    timestamps = _build_word_timestamps(alignment)

    duration_ms = int(max(
        (t.end_ms for t in timestamps), default=0
    )) if timestamps else len(script) * 60  # fallback estimé

    return ElevenLabsResult(
        audio_path=audio_path,
        audio_duration_ms=duration_ms,
        timestamps=timestamps,
        voice_id=voice_id,
        character_count=len(script),
    )


def _save_audio(audio_bytes: bytes) -> str:
    Path(AUDIO_STORAGE_DIR).mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4()}.mp3"
    path = os.path.join(AUDIO_STORAGE_DIR, filename)
    with open(path, "wb") as f:
        f.write(audio_bytes)
    return path


def _build_word_timestamps(alignment: dict) -> list[WordTimestamp]:
    """
    Convertit le format character-level ElevenLabs en mots.
    ElevenLabs retourne char par char — on regroupe par espace.
    """
    chars = alignment.get("characters", [])
    starts = alignment.get("character_start_times_seconds", [])
    ends = alignment.get("character_end_times_seconds", [])

    if not chars:
        return []

    words: list[WordTimestamp] = []
    current_word = ""
    word_start_ms = 0

    for char, start_s, end_s in zip(chars, starts, ends):
        if char == " " or char == "\n":
            if current_word:
                words.append(WordTimestamp(
                    word=current_word,
                    start_ms=word_start_ms,
                    end_ms=int(end_s * 1000),
                ))
                current_word = ""
        else:
            if not current_word:
                word_start_ms = int(start_s * 1000)
            current_word += char

    if current_word:  # dernier mot sans espace final
        words.append(WordTimestamp(
            word=current_word,
            start_ms=word_start_ms,
            end_ms=int(ends[-1] * 1000) if ends else word_start_ms + 500,
        ))

    return words
```

### Step 2.4 — Vérifier les tests

```bash
python -m pytest tests/test_elevenlabs.py tests/test_claude.py -v
```
Attendu : **4 passed**

### Step 2.5 — Suite complète

```bash
python -m pytest tests/ -v
```
Attendu : **19 passed**

### Step 2.6 — Commit

```bash
git add app/elevenlabs.py tests/test_elevenlabs.py
git commit -m "feat: implement elevenlabs.py — voiceover + word timestamps with retry"
```

---

## Task 3 — `kling.py` : Génération clips asynchrone

**PRD §4.3** — JWT auth, asyncio.gather + Semaphore (max 5), polling 30s, timeout 10min, retry x3, fallback Pexels.

**Files:**
- Modify: `app/kling.py`
- Create: `tests/test_kling.py`

---

### Step 3.1 — Écrire les tests

```python
# tests/test_kling.py
import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch
import httpx

from tests.test_claude import MINIMAL_ENV

@pytest.fixture
def env_vars(monkeypatch):
    for k, v in MINIMAL_ENV.items():
        monkeypatch.setenv(k, v)

def _make_section(id_=1, keywords=None):
    from app.models import ScriptSection
    return ScriptSection(
        id=id_, text="test", start=(id_-1)*5, end=id_*5, duration=5,
        broll_prompt=f"entrepreneur bureau lumière 9:16 section {id_}",
        keywords=keywords or ["entrepreneur"],
    )

def _kling_created_response(task_id="task-abc"):
    m = MagicMock(spec=httpx.Response)
    m.status_code = 200
    m.raise_for_status = MagicMock()
    m.json.return_value = {"code": 0, "data": {"task_id": task_id, "task_status": "submitted"}}
    return m

def _kling_done_response(task_id="task-abc", video_url="https://kling.cdn/clip.mp4"):
    m = MagicMock(spec=httpx.Response)
    m.status_code = 200
    m.raise_for_status = MagicMock()
    m.json.return_value = {
        "code": 0,
        "data": {
            "task_id": task_id,
            "task_status": "succeed",
            "task_result": {"videos": [{"url": video_url, "duration": "5.0"}]},
        }
    }
    return m

@pytest.mark.asyncio
async def test_generate_single_clip_success(env_vars):
    from app.kling import generate_single_clip
    from app.models import VideoFormat, ClipSource
    from app.config import Settings
    settings = Settings()

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = _kling_created_response()
    mock_client.get.return_value = _kling_done_response()

    with patch("app.kling.asyncio.sleep", new=AsyncMock()):
        clip = await generate_single_clip(_make_section(), VideoFormat.VERTICAL, mock_client, settings)

    assert clip.source == ClipSource.KLING
    assert clip.url == "https://kling.cdn/clip.mp4"
    assert clip.section_id == 1

@pytest.mark.asyncio
async def test_generate_clips_respects_semaphore(env_vars):
    """Vérifie que max KLING_MAX_PARALLEL_JOBS clips tournent simultanément."""
    from app.kling import generate_clips
    from app.models import VideoFormat
    from app.config import Settings
    settings = Settings()

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = [_kling_created_response(f"t{i}") for i in range(7)]
    mock_client.get.side_effect = [_kling_done_response(f"t{i}", f"https://cdn/{i}.mp4") for i in range(7)]

    sections = [_make_section(i) for i in range(1, 8)]  # 7 sections > max 5 parallel

    with patch("app.kling.asyncio.sleep", new=AsyncMock()):
        clips = await generate_clips(sections, VideoFormat.VERTICAL, mock_client, settings)

    assert len(clips) == 7
    assert all(c.source.value == "kling" for c in clips)

@pytest.mark.asyncio
async def test_generate_single_clip_retries_then_raises(env_vars):
    from app.kling import generate_single_clip
    from app.models import VideoFormat
    from app.config import Settings
    from app.errors import KlingMaxRetriesError
    settings = Settings()

    failed_resp = MagicMock(spec=httpx.Response)
    failed_resp.raise_for_status = MagicMock()
    failed_resp.json.return_value = {"code": 0, "data": {"task_id": "t1", "task_status": "submitted"}}

    failed_status = MagicMock(spec=httpx.Response)
    failed_status.raise_for_status = MagicMock()
    failed_status.json.return_value = {"code": 0, "data": {"task_id": "t1", "task_status": "failed"}}

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = failed_resp
    mock_client.get.return_value = failed_status

    with patch("app.kling.asyncio.sleep", new=AsyncMock()):
        with pytest.raises(KlingMaxRetriesError):
            await generate_single_clip(_make_section(), VideoFormat.VERTICAL, mock_client, settings, attempt=settings.KLING_MAX_RETRIES)
```

### Step 3.2 — Vérifier l'échec

```bash
python -m pytest tests/test_kling.py -v
```
Attendu : **FAIL** — `NotImplementedError`

### Step 3.3 — Implémenter `app/kling.py`

```python
"""
kling.py — Module génération clips IA asynchrone (PRD §4.3)
"""
import asyncio
import logging
import time
from collections.abc import Callable

import httpx
import jwt

from app.config import Settings
from app.errors import KlingAPIError, KlingClipTimeoutError, KlingMaxRetriesError, KlingUnavailableError
from app.models import ClipSource, ScriptSection, VideoClip, VideoFormat

logger = logging.getLogger(__name__)


def _build_kling_jwt(access_key: str, secret_key: str) -> str:
    now = int(time.time())
    payload = {"iss": access_key, "exp": now + 1800, "nbf": now - 5}
    return jwt.encode(payload, secret_key, algorithm="HS256")


def _kling_headers(settings: Settings) -> dict:
    token = _build_kling_jwt(settings.kling_access_key, settings.kling_secret_key)
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def generate_clips(
    sections: list[ScriptSection],
    format_: VideoFormat,
    http_client: httpx.AsyncClient,
    settings: Settings,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[VideoClip]:
    semaphore = asyncio.Semaphore(settings.KLING_MAX_PARALLEL_JOBS)
    done_count = 0
    total = len(sections)
    results: list[VideoClip | Exception] = [None] * total  # type: ignore

    async def run_one(idx: int, section: ScriptSection):
        nonlocal done_count
        async with semaphore:
            try:
                clip = await generate_single_clip(section, format_, http_client, settings)
                results[idx] = clip
            except Exception as e:
                logger.error("Clip section %d échoué après retries : %s", section.id, e)
                results[idx] = e
            finally:
                done_count += 1
                if progress_callback:
                    progress_callback(done_count, total)

    await asyncio.gather(*[run_one(i, s) for i, s in enumerate(sections)])

    # Fallback Pexels pour les clips échoués
    clips: list[VideoClip] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning("Fallback Pexels pour section %d", sections[i].id)
            fallback = await _pexels_fallback(sections[i], format_, http_client, settings)
            clips.append(fallback)
        else:
            clips.append(result)  # type: ignore

    return sorted(clips, key=lambda c: c.section_id)


async def generate_single_clip(
    section: ScriptSection,
    format_: VideoFormat,
    http_client: httpx.AsyncClient,
    settings: Settings,
    attempt: int = 1,
) -> VideoClip:
    if attempt > settings.KLING_MAX_RETRIES:
        raise KlingMaxRetriesError(
            f"Section {section.id} : max retries ({settings.KLING_MAX_RETRIES}) atteint"
        )

    aspect = "9:16" if format_ == VideoFormat.VERTICAL else "16:9"

    try:
        create_resp = await http_client.post(
            f"{settings.KLING_BASE_URL}/v1/videos/text2video",
            headers=_kling_headers(settings),
            json={"model_name": settings.KLING_MODEL, "prompt": section.broll_prompt,
                  "duration": settings.KLING_DURATION, "aspect_ratio": aspect},
            timeout=30.0,
        )
        create_resp.raise_for_status()
        data = create_resp.json()
        task_id = data["data"]["task_id"]
        logger.info("Kling job créé : task_id=%s section=%d", task_id, section.id)

    except httpx.HTTPStatusError as e:
        if e.response.status_code in (429, 503):
            raise KlingUnavailableError(f"Kling indisponible : HTTP {e.response.status_code}")
        raise KlingAPIError(f"Kling create error HTTP {e.response.status_code} : {e}")

    # Polling
    elapsed = 0.0
    while elapsed < settings.KLING_CLIP_TIMEOUT:
        await asyncio.sleep(settings.KLING_POLLING_INTERVAL)
        elapsed += settings.KLING_POLLING_INTERVAL

        poll_resp = await http_client.get(
            f"{settings.KLING_BASE_URL}/v1/videos/text2video/{task_id}",
            headers=_kling_headers(settings),
            timeout=15.0,
        )
        poll_resp.raise_for_status()
        poll_data = poll_resp.json()["data"]
        status_str = poll_data["task_status"]

        if status_str == "succeed":
            video_url = poll_data["task_result"]["videos"][0]["url"]
            duration_s = float(poll_data["task_result"]["videos"][0].get("duration", settings.KLING_DURATION))
            logger.info("Kling clip OK : task_id=%s section=%d url=%s", task_id, section.id, video_url)
            return VideoClip(section_id=section.id, source=ClipSource.KLING,
                             url=video_url, duration_seconds=duration_s, prompt_used=section.broll_prompt)

        if status_str == "failed":
            if attempt < settings.KLING_MAX_RETRIES:
                logger.warning("Kling clip failed, retry %d/%d section %d", attempt, settings.KLING_MAX_RETRIES, section.id)
                return await generate_single_clip(section, format_, http_client, settings, attempt + 1)
            raise KlingMaxRetriesError(f"Section {section.id} Kling failed après {attempt} tentatives")

        logger.debug("Kling polling task=%s status=%s elapsed=%.0fs", task_id, status_str, elapsed)

    raise KlingClipTimeoutError(
        f"Section {section.id} : timeout {settings.KLING_CLIP_TIMEOUT}s dépassé",
    )


async def _pexels_fallback(
    section: ScriptSection,
    format_: VideoFormat,
    http_client: httpx.AsyncClient,
    settings: Settings,
) -> VideoClip:
    """Fallback Pexels quand Kling échoue définitivement."""
    orientation = "portrait" if format_ == VideoFormat.VERTICAL else "landscape"
    query = " ".join(section.keywords[:3]) if section.keywords else section.broll_prompt[:50]

    try:
        resp = await http_client.get(
            f"{settings.PEXELS_BASE_URL}/videos/search",
            headers={"Authorization": settings.pexels_api_key},
            params={"query": query, "per_page": 5, "orientation": orientation},
            timeout=15.0,
        )
        resp.raise_for_status()
        videos = resp.json().get("videos", [])
        if videos:
            best = videos[0]
            file_url = best["video_files"][0]["link"]
            return VideoClip(section_id=section.id, source=ClipSource.PEXELS,
                             url=file_url, duration_seconds=float(best.get("duration", 5)),
                             keywords_used=section.keywords)
    except Exception as e:
        logger.error("Pexels fallback échoué pour section %d : %s", section.id, e)

    # Si même Pexels échoue : clip vide (Creatomate gérera)
    return VideoClip(section_id=section.id, source=ClipSource.PEXELS,
                     url="", duration_seconds=float(settings.KLING_DURATION))
```

### Step 3.4 — Vérifier les tests

```bash
python -m pytest tests/test_kling.py -v
```
Attendu : **3 passed**

### Step 3.5 — Suite complète

```bash
python -m pytest tests/ -v
```
Attendu : **22 passed**

### Step 3.6 — Commit

```bash
git add app/kling.py tests/test_kling.py
git commit -m "feat: implement kling.py — async clip generation with semaphore, retry, pexels fallback"
```

---

## Task 4 — `library.py` : Bibliothèque clips + Pexels (Stratégie B)

**PRD §3** — Pour chaque section : Library (score Claude ≥ 0.7) → Pexels → Kling. Index JSON sur VPS.

**Files:**
- Modify: `app/library.py`
- Create: `tests/test_library.py`

---

### Step 4.1 — Écrire les tests

```python
# tests/test_library.py
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from tests.test_claude import MINIMAL_ENV

@pytest.fixture
def env_vars(monkeypatch):
    for k, v in MINIMAL_ENV.items():
        monkeypatch.setenv(k, v)

@pytest.fixture
def library_dir(tmp_path):
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir()
    return tmp_path

def _make_section(id_=1):
    from app.models import ScriptSection
    return ScriptSection(id=id_, text="Entrepreneur", start=0, end=5, duration=5,
                         broll_prompt="entrepreneur bureau 9:16", keywords=["entrepreneur", "bureau"])

@pytest.mark.asyncio
async def test_library_search_returns_match_above_threshold(env_vars, library_dir, monkeypatch):
    from app.library import library_search
    from app.config import Settings
    from app.models import VideoFormat, LibraryClip

    monkeypatch.setenv("LIBRARY_INDEX_FILE", str(library_dir / "index.json"))
    settings = Settings()

    existing_clip = LibraryClip(
        clip_id="clip-1", filename="entrepreneur_01.mp4",
        theme="entrepreneur", keywords=["entrepreneur", "bureau"],
        duration_seconds=5.0, format=VideoFormat.VERTICAL
    )
    (library_dir / "index.json").write_text(
        json.dumps([existing_clip.model_dump(mode="json")])
    )

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text='{"score": 0.85, "reason": "Correspondance directe"}')]

    with patch("app.library.anthropic.AsyncAnthropic") as mock_anthro:
        mock_client_instance = AsyncMock()
        mock_client_instance.messages.create = AsyncMock(return_value=mock_message)
        mock_anthro.return_value = mock_client_instance

        result = await library_search(_make_section(), VideoFormat.VERTICAL, settings)

    assert result is not None
    assert result.relevance_score >= 0.7
    assert result.clip.clip_id == "clip-1"

@pytest.mark.asyncio
async def test_library_search_returns_none_below_threshold(env_vars, library_dir, monkeypatch):
    from app.library import library_search
    from app.config import Settings
    from app.models import VideoFormat, LibraryClip

    monkeypatch.setenv("LIBRARY_INDEX_FILE", str(library_dir / "index.json"))
    settings = Settings()

    (library_dir / "index.json").write_text(json.dumps([
        LibraryClip(clip_id="c1", filename="f.mp4", theme="cuisine",
                    keywords=["cuisine"], duration_seconds=5.0, format=VideoFormat.VERTICAL
                    ).model_dump(mode="json")
    ]))

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text='{"score": 0.3, "reason": "Thème différent"}')]

    with patch("app.library.anthropic.AsyncAnthropic") as mock_anthro:
        instance = AsyncMock()
        instance.messages.create = AsyncMock(return_value=mock_message)
        mock_anthro.return_value = instance
        result = await library_search(_make_section(), VideoFormat.VERTICAL, settings)

    assert result is None
```

### Step 4.2 — Vérifier l'échec

```bash
python -m pytest tests/test_library.py -v
```
Attendu : **FAIL** — `NotImplementedError`

### Step 4.3 — Implémenter `app/library.py`

```python
"""
library.py — Bibliothèque clips locale + cascade Stratégie B (PRD §3)
"""
import json
import logging
from collections.abc import Callable
from pathlib import Path

import anthropic
import httpx

from app.config import Settings
from app.models import (ClipSource, LibraryClip, LibrarySearchResult,
                        ScriptSection, VideoClip, VideoFormat)

logger = logging.getLogger(__name__)


def load_library_index(settings: Settings) -> list[LibraryClip]:
    index_path = Path(settings.LIBRARY_INDEX_FILE)
    if not index_path.exists():
        return []
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
        return [LibraryClip(**item) for item in data]
    except Exception as e:
        logger.error("Erreur lecture index bibliothèque : %s", e)
        return []


def save_library_index(clips: list[LibraryClip], settings: Settings) -> None:
    index_path = Path(settings.LIBRARY_INDEX_FILE)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps([c.model_dump(mode="json") for c in clips], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


async def library_search(
    section: ScriptSection,
    format_: VideoFormat,
    settings: Settings,
) -> LibrarySearchResult | None:
    clips = load_library_index(settings)
    candidates = [c for c in clips if c.format == format_]
    if not candidates:
        return None

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    clips_summary = "\n".join(
        f"- id:{c.clip_id} theme:{c.theme} keywords:{c.keywords}"
        for c in candidates[:20]  # limite pour ne pas exploser le contexte
    )
    prompt = (
        f"Section vidéo : '{section.text}'\n"
        f"Keywords : {section.keywords}\n\n"
        f"Clips disponibles :\n{clips_summary}\n\n"
        "Quel clip correspond le mieux ? Réponds en JSON : "
        '{"score": <0.0-1.0>, "clip_id": "<id ou null>", "reason": "<explication>"}'
    )
    try:
        response = await client.messages.create(
            model=settings.CLAUDE_MODEL, max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        data = json.loads(response.content[0].text)
        score = float(data.get("score", 0))
        if score < settings.LIBRARY_SCORE_THRESHOLD:
            return None
        clip_id = data.get("clip_id")
        matched = next((c for c in candidates if c.clip_id == clip_id), None)
        if not matched:
            return None
        return LibrarySearchResult(
            clip=matched, relevance_score=score,
            matched_keywords=[k for k in section.keywords if k in matched.keywords],
        )
    except Exception as e:
        logger.warning("library_search Claude error : %s", e)
        return None


async def pexels_search(
    section: ScriptSection,
    format_: VideoFormat,
    http_client: httpx.AsyncClient,
    settings: Settings,
) -> VideoClip | None:
    orientation = "portrait" if format_ == VideoFormat.VERTICAL else "landscape"
    query = " ".join(section.keywords[:3]) if section.keywords else section.text[:40]
    try:
        resp = await http_client.get(
            f"{settings.PEXELS_BASE_URL}/videos/search",
            headers={"Authorization": settings.pexels_api_key},
            params={"query": query, "per_page": 5, "orientation": orientation},
            timeout=15.0,
        )
        resp.raise_for_status()
        videos = resp.json().get("videos", [])
        if not videos:
            return None
        best = videos[0]
        file_url = best["video_files"][0]["link"]
        return VideoClip(section_id=section.id, source=ClipSource.PEXELS,
                         url=file_url, duration_seconds=float(best.get("duration", 5)),
                         keywords_used=section.keywords)
    except Exception as e:
        logger.warning("Pexels search erreur section %d : %s", section.id, e)
        return None


async def add_to_library(clip: VideoClip, section: ScriptSection, settings: Settings) -> LibraryClip:
    from app.models import VideoFormat
    clips = load_library_index(settings)
    lib_clip = LibraryClip(
        filename=clip.url.split("/")[-1] if clip.url else f"{section.id}.mp4",
        theme=section.scene_type.value,
        keywords=section.keywords,
        duration_seconds=clip.duration_seconds,
        format=VideoFormat.VERTICAL,  # déduire du clip si possible
    )
    clips.append(lib_clip)
    save_library_index(clips, settings)
    logger.info("Clip ajouté à la bibliothèque : %s", lib_clip.clip_id)
    return lib_clip


async def select_library_clips(
    sections: list[ScriptSection],
    format_: VideoFormat,
    http_client: httpx.AsyncClient,
    settings: Settings,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[VideoClip]:
    from app.kling import generate_single_clip
    clips: list[VideoClip] = []
    total = len(sections)

    for i, section in enumerate(sections):
        clip: VideoClip | None = None

        # 1. Bibliothèque locale
        lib_result = await library_search(section, format_, settings)
        if lib_result:
            logger.info("Library hit section %d score=%.2f", section.id, lib_result.relevance_score)
            clip = VideoClip(
                section_id=section.id, source=ClipSource.LIBRARY,
                url=str(Path(settings.LIBRARY_PATH) / lib_result.clip.filename),
                duration_seconds=lib_result.clip.duration_seconds,
                library_clip_id=lib_result.clip.clip_id,
            )
        # 2. Pexels fallback
        if clip is None:
            clip = await pexels_search(section, format_, http_client, settings)
            if clip:
                logger.info("Pexels hit section %d", section.id)

        # 3. Kling dernier recours
        if clip is None:
            logger.info("Kling generation section %d (aucun clip en bibliothèque/Pexels)", section.id)
            try:
                clip = await generate_single_clip(section, format_, http_client, settings)
                await add_to_library(clip, section, settings)
            except Exception as e:
                logger.error("Kling échec section %d : %s — clip vide", section.id, e)
                clip = VideoClip(section_id=section.id, source=ClipSource.KLING,
                                 url="", duration_seconds=float(settings.KLING_DURATION))

        clips.append(clip)
        if progress_callback:
            progress_callback(i + 1, total)

    return clips
```

### Step 4.4 — Vérifier les tests

```bash
python -m pytest tests/test_library.py -v
```
Attendu : **2 passed**

### Step 4.5 — Suite complète

```bash
python -m pytest tests/ -v
```
Attendu : **24 passed**

### Step 4.6 — Commit

```bash
git add app/library.py tests/test_library.py
git commit -m "feat: implement library.py — strategy B clip cascade (library → pexels → kling)"
```

---

## Task 5 — `creatomate.py` : Assemblage vidéo final

**PRD §4.4** — Templates vertical/horizontal, sous-titres mot par mot, logo, CTA, musique. Polling 15s, retry x2.

**Files:**
- Modify: `app/creatomate.py`
- Create: `tests/test_creatomate.py`

---

### Step 5.1 — Écrire les tests

```python
# tests/test_creatomate.py
import pytest
from unittest.mock import AsyncMock, MagicMock
import httpx

from tests.test_claude import MINIMAL_ENV
from app.models import (ElevenLabsResult, ScriptSection, ScriptAnalysis,
                         VideoClip, ClipSource, VideoFormat, WordTimestamp)

@pytest.fixture
def env_vars(monkeypatch):
    for k, v in MINIMAL_ENV.items():
        monkeypatch.setenv(k, v)

def _make_render_request():
    from app.models import CreatomateRenderRequest
    return CreatomateRenderRequest(
        template_id="tmpl-v",
        audio_url="/tmp/audio.mp3",
        clips=[
            VideoClip(section_id=1, source=ClipSource.KLING,
                      url="https://cdn/clip1.mp4", duration_seconds=5.0),
            VideoClip(section_id=2, source=ClipSource.PEXELS,
                      url="https://cdn/clip2.mp4", duration_seconds=5.0),
        ],
        timestamps=[
            WordTimestamp(word="Hello", start_ms=0, end_ms=500),
            WordTimestamp(word="world", start_ms=600, end_ms=1100),
        ],
        cta_text="Contactez-nous",
        format=VideoFormat.VERTICAL,
    )

@pytest.mark.asyncio
async def test_assemble_video_returns_render_result(env_vars):
    from app.creatomate import assemble_video
    from app.config import Settings
    settings = Settings()

    submitted = MagicMock(spec=httpx.Response)
    submitted.raise_for_status = MagicMock()
    submitted.json.return_value = [{"id": "render-123", "status": "planned"}]

    done = MagicMock(spec=httpx.Response)
    done.raise_for_status = MagicMock()
    done.json.return_value = {"id": "render-123", "status": "succeeded",
                               "url": "https://cdn/final.mp4", "duration": 10.0, "file_size": 5000000}

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = submitted
    mock_client.get.return_value = done

    from app.models import SheetsRow
    row = SheetsRow(row_id="r1", script="A" * 50, voice_id="v1",
                    duration=10, cta="Contactez-nous")
    analysis = ScriptAnalysis(
        total_duration=10,
        sections=[
            ScriptSection(id=1, text="p1", start=0, end=5, duration=5,
                          broll_prompt="entrepreneur bureau lumière 9:16"),
            ScriptSection(id=2, text="p2", start=5, end=10, duration=5,
                          broll_prompt="produit gros plan 9:16"),
        ]
    )
    el_result = ElevenLabsResult(audio_path="/tmp/a.mp3", audio_duration_ms=10000,
                                  timestamps=[], voice_id="v1", character_count=100)
    clips = [VideoClip(section_id=i, source=ClipSource.KLING,
                        url=f"https://cdn/{i}.mp4", duration_seconds=5.0) for i in [1, 2]]

    import unittest.mock
    with unittest.mock.patch("app.creatomate.asyncio.sleep", new=AsyncMock()):
        result = await assemble_video(analysis, el_result, clips, row, mock_client, settings)

    assert result.render_id == "render-123"
    assert result.video_url == "https://cdn/final.mp4"
```

### Step 5.2 — Vérifier l'échec

```bash
python -m pytest tests/test_creatomate.py -v
```
Attendu : **FAIL** — `NotImplementedError`

### Step 5.3 — Implémenter `app/creatomate.py`

```python
"""
creatomate.py — Assemblage vidéo final (PRD §4.4)
"""
import asyncio
import logging

import httpx

from app.config import Settings
from app.errors import CreatomateAPIError, CreatomateRenderTimeoutError
from app.models import (CreatomateRenderRequest, CreatomateRenderResult,
                         ElevenLabsResult, ScriptAnalysis, SheetsRow,
                         VideoClip, VideoFormat, WordTimestamp)

logger = logging.getLogger(__name__)


async def assemble_video(
    script_analysis: ScriptAnalysis,
    elevenlabs_result: ElevenLabsResult,
    clips: list[VideoClip],
    row: SheetsRow,
    http_client: httpx.AsyncClient,
    settings: Settings,
) -> CreatomateRenderResult:
    template_id = (settings.CREATOMATE_TEMPLATE_VERTICAL
                   if row.format == VideoFormat.VERTICAL
                   else settings.CREATOMATE_TEMPLATE_HORIZONTAL)

    request = CreatomateRenderRequest(
        template_id=template_id,
        audio_url=elevenlabs_result.audio_path,
        clips=sorted(clips, key=lambda c: c.section_id),
        timestamps=elevenlabs_result.timestamps,
        logo_url=row.logo_url or settings.LOGO_URL,
        cta_text=row.cta,
        music_url=row.music_url,
        format=row.format,
    )

    last_error: Exception | None = None
    for attempt in range(settings.CREATOMATE_MAX_RETRIES + 1):
        try:
            render_id = await _submit_render(request, http_client, settings)
            result = await _poll_render(render_id, request.format, http_client, settings)
            return result
        except CreatomateRenderTimeoutError:
            raise
        except Exception as e:
            last_error = e
            logger.warning("Creatomate tentative %d/%d échouée : %s",
                           attempt + 1, settings.CREATOMATE_MAX_RETRIES + 1, e)
            if attempt < settings.CREATOMATE_MAX_RETRIES:
                await asyncio.sleep(5.0)

    raise CreatomateAPIError(
        f"Creatomate échec après {settings.CREATOMATE_MAX_RETRIES + 1} tentatives : {last_error}"
    )


async def _submit_render(
    request: CreatomateRenderRequest,
    http_client: httpx.AsyncClient,
    settings: Settings,
) -> str:
    payload = _build_render_payload(request, settings)
    resp = await http_client.post(
        f"{settings.CREATOMATE_BASE_URL}/renders",
        headers={"Authorization": f"Bearer {settings.creatomate_api_key}",
                 "Content-Type": "application/json"},
        json=payload,
        timeout=30.0,
    )
    resp.raise_for_status()
    renders = resp.json()
    render_id = renders[0]["id"]
    logger.info("Creatomate render soumis : render_id=%s", render_id)
    return render_id


async def _poll_render(
    render_id: str,
    format_: VideoFormat,
    http_client: httpx.AsyncClient,
    settings: Settings,
) -> CreatomateRenderResult:
    elapsed = 0.0
    while elapsed < settings.CREATOMATE_RENDER_TIMEOUT:
        await asyncio.sleep(settings.CREATOMATE_POLLING_INTERVAL)
        elapsed += settings.CREATOMATE_POLLING_INTERVAL

        resp = await http_client.get(
            f"{settings.CREATOMATE_BASE_URL}/renders/{render_id}",
            headers={"Authorization": f"Bearer {settings.creatomate_api_key}"},
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        status = data["status"]

        if status == "succeeded":
            logger.info("Creatomate render terminé : %s", render_id)
            return CreatomateRenderResult(
                render_id=render_id,
                video_url=data["url"],
                duration_seconds=float(data.get("duration", 0)),
                file_size_bytes=data.get("file_size"),
                format=format_,
            )
        if status == "failed":
            raise CreatomateAPIError(f"Creatomate render {render_id} a échoué : {data.get('error_message')}")

        logger.debug("Creatomate polling render=%s status=%s elapsed=%.0fs", render_id, status, elapsed)

    raise CreatomateRenderTimeoutError(
        f"Render {render_id} timeout après {settings.CREATOMATE_RENDER_TIMEOUT}s"
    )


def _build_render_payload(request: CreatomateRenderRequest, settings: Settings) -> dict:
    modifications: dict = {}
    for i, clip in enumerate(request.clips):
        modifications[f"clip_{i + 1}"] = clip.url

    modifications["voiceover"] = request.audio_url

    if request.logo_url:
        modifications["logo"] = request.logo_url
    if request.cta_text:
        modifications["cta_text"] = request.cta_text
    if request.music_url:
        modifications["music"] = request.music_url

    if request.timestamps:
        modifications["subtitles"] = _timestamps_to_creatomate_subtitles(request.timestamps)

    return {"template_id": request.template_id, "modifications": modifications}


def _timestamps_to_creatomate_subtitles(timestamps: list[WordTimestamp]) -> list[dict]:
    """
    Convertit [{word, start_ms, end_ms}] en format Creatomate pour sous-titres animés.
    PRD §4.4 : chaque mot apparaît exactement au moment où il est prononcé.
    """
    return [
        {
            "text": ts.word,
            "time": ts.start_ms / 1000.0,
            "duration": (ts.end_ms - ts.start_ms) / 1000.0,
        }
        for ts in timestamps
    ]
```

### Step 5.4 — Vérifier les tests

```bash
python -m pytest tests/test_creatomate.py -v
```
Attendu : **1 passed**

### Step 5.5 — Suite complète

```bash
python -m pytest tests/ -v
```
Attendu : **25 passed**

### Step 5.6 — Commit

```bash
git add app/creatomate.py tests/test_creatomate.py
git commit -m "feat: implement creatomate.py — video assembly with subtitle sync and retry"
```

---

## Task 6 — Pipeline global timeout + test d'intégration

**Résout I2** — Wrapper `run_pipeline` avec `asyncio.timeout`. Test intégration pipeline complet mocké.

**Files:**
- Modify: `app/main.py`
- Create: `tests/test_integration.py`

---

### Step 6.1 — Écrire le test d'intégration

```python
# tests/test_integration.py
"""Test du pipeline complet avec tous les modules mockés."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from tests.test_claude import MINIMAL_ENV, VALID_CLAUDE_JSON

@pytest.fixture
def env_vars(monkeypatch):
    for k, v in MINIMAL_ENV.items():
        monkeypatch.setenv(k, v)

@pytest.mark.asyncio
async def test_full_pipeline_strategy_a(env_vars, tmp_path, monkeypatch):
    """Test pipeline Strategy A : Claude → ElevenLabs → Kling → Creatomate."""
    import base64
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.config import Settings
    from app.models import JobStatus

    monkeypatch.setenv("LIBRARY_PATH", str(tmp_path / "clips"))

    # Mocks de tous les modules
    mock_analysis = MagicMock()
    mock_analysis.sections = []
    mock_analysis.section_count = 0
    mock_analysis.total_duration = 10

    mock_el = MagicMock()
    mock_el.audio_path = "/tmp/audio.mp3"
    mock_el.audio_duration_seconds = 10.0
    mock_el.timestamps = []

    mock_clips = []
    mock_render = MagicMock()
    mock_render.render_id = "render-xyz"
    mock_render.video_url = "https://cdn/final.mp4"
    mock_render.duration_seconds = 10.0

    settings = Settings()

    with (
        patch("app.main.analyze_script", return_value=mock_analysis) as p_claude,
        patch("app.main.generate_voiceover", return_value=mock_el) as p_el,
        patch("app.main.generate_clips", return_value=mock_clips) as p_kling,
        patch("app.main.assemble_video", return_value=mock_render) as p_creat,
    ):
        with TestClient(create_app(settings)) as client:
            resp = client.post(
                "/generate",
                headers={"Authorization": f"Bearer {settings.api_secret_key}"},
                json={
                    "sheets_row": {
                        "row_id": "row_1",
                        "script": "Script de test complet pour le pipeline. " * 3,
                        "format": "vertical",
                        "strategy": "A",
                        "duration": 90,
                        "voice_id": "voice-test",
                        "cta": "Contactez-nous",
                    }
                }
            )
            assert resp.status_code == 202
            job_id = resp.json()["job_id"]

    # Les mocks ont été appelés
    p_claude.assert_called_once()
    p_el.assert_called_once()
    p_kling.assert_called_once()
    p_creat.assert_called_once()
```

### Step 6.2 — Ajouter global timeout dans `run_pipeline`

Dans `app/main.py`, modifier le début de `run_pipeline` :

```python
async def run_pipeline(job_id, app, settings):
    job = app.state.jobs[job_id]
    http_client = app.state.http_client
    request = job.request
    row = request.sheets_row

    try:
        async with asyncio.timeout(settings.HTTP_TIMEOUT_VIDEO_GEN):  # garde-fou global
            # ... reste du pipeline inchangé
```

Ajouter `import asyncio` si absent en tête de `main.py`.

### Step 6.3 — Lancer les tests d'intégration

```bash
python -m pytest tests/test_integration.py -v
```
Attendu : **1 passed**

### Step 6.4 — Suite complète

```bash
python -m pytest tests/ -v
```
Attendu : **26 passed**

### Step 6.5 — Commit

```bash
git add app/main.py tests/test_integration.py
git commit -m "feat: add global pipeline timeout + integration test (full mock pipeline)"
```

---

## Task 7 — Workflow n8n

**PRD §2.1** — n8n détecte statut=OK dans Sheets, appelle FastAPI, upload Drive, notifie.

**Files:**
- Create: `n8n/workflow_videogen.json` (à importer dans n8n)
- Create: `docs/n8n-setup.md`

### Step 7.1 — Créer le workflow JSON n8n

```json
// n8n/workflow_videogen.json
// Importer via : n8n UI → Import → coller le JSON

{
  "name": "VideoGen Pipeline",
  "nodes": [
    {
      "name": "Sheets Trigger",
      "type": "n8n-nodes-base.googleSheetsTrigger",
      "parameters": {
        "sheetId": "={{ $env.GOOGLE_SHEETS_ID }}",
        "range": "Campagnes!A:J",
        "pollTimes": { "item": [{"mode": "everyMinute"}] }
      }
    },
    {
      "name": "Filter status=OK",
      "type": "n8n-nodes-base.filter",
      "parameters": {
        "conditions": {
          "string": [{"value1": "={{ $json['Statut'] }}", "operation": "equals", "value2": "OK"}]
        }
      }
    },
    {
      "name": "Update status En cours",
      "type": "n8n-nodes-base.googleSheets",
      "parameters": {
        "operation": "update",
        "sheetId": "={{ $env.GOOGLE_SHEETS_ID }}",
        "range": "Campagnes",
        "columns": {"Statut": "En cours", "Statut détail": "Job soumis à l'API"}
      }
    },
    {
      "name": "POST /generate",
      "type": "n8n-nodes-base.httpRequest",
      "parameters": {
        "method": "POST",
        "url": "http://localhost:8000/generate",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "headers": {"Authorization": "Bearer {{ $env.VIDEOGEN_API_SECRET }}"},
        "body": {
          "sheets_row": {
            "row_id": "={{ $json['row_id'] }}",
            "script": "={{ $json['Script'] }}",
            "format": "={{ $json['Format'] }}",
            "strategy": "={{ $json['Stratégie'] }}",
            "duration": "={{ $json['Durée cible'] }}",
            "voice_id": "={{ $json['Voix'] }}",
            "music_url": "={{ $json['Musique'] }}",
            "cta": "={{ $json['CTA'] }}"
          },
          "webhook_url": "http://localhost:5678/webhook/videogen-callback"
        }
      }
    },
    {
      "name": "Webhook Callback",
      "type": "n8n-nodes-base.webhook",
      "parameters": {
        "path": "videogen-callback",
        "responseMode": "lastNode"
      }
    },
    {
      "name": "Upload Google Drive",
      "type": "n8n-nodes-base.googleDrive",
      "parameters": {
        "operation": "upload",
        "name": "={{ $json['row_id'] }}_pub.mp4",
        "parents": ["={{ $env.GOOGLE_DRIVE_FOLDER_ID }}"],
        "binaryData": false,
        "fileUrl": "={{ $json['drive_url'] }}"
      }
    },
    {
      "name": "Update Sheets Livré",
      "type": "n8n-nodes-base.googleSheets",
      "parameters": {
        "operation": "update",
        "sheetId": "={{ $env.GOOGLE_SHEETS_ID }}",
        "columns": {
          "Statut": "Livré",
          "Lien output": "={{ $json['webViewLink'] }}",
          "Statut détail": "Pub générée avec succès"
        }
      }
    }
  ]
}
```

### Step 7.2 — Tester manuellement dans n8n

```bash
# 1. Démarrer l'API en dev
make dev

# 2. Dans n8n : importer workflow_videogen.json
# 3. Ajouter une ligne dans Sheets avec Statut=OK et données valides
# 4. Vérifier dans n8n que le workflow se déclenche
# 5. Vérifier le job_id retourné et GET /status/{job_id}
```

### Step 7.3 — Commit

```bash
git add n8n/ docs/n8n-setup.md
git commit -m "feat: n8n workflow — sheets trigger, api call, drive upload, status update"
```

---

## Task 8 — Déploiement VPS Ubuntu

**PRD §2.2** — systemd + gunicorn sur VPS, nginx reverse proxy.

**Files:**
- Already created: `systemd/videogen.service`
- Create: `docs/deployment.md`

### Step 8.1 — Déploiement

```bash
# Sur le VPS Ubuntu (SSH)

# 1. Prérequis
sudo apt install python3.12 python3.12-venv nginx -y

# 2. Créer utilisateur dédié
sudo useradd -r -m -d /opt/videogen videogen

# 3. Cloner/copier le code
sudo -u videogen git clone <repo> /opt/videogen/api

# 4. Virtualenv
sudo -u videogen python3.12 -m venv /opt/videogen/venv
sudo -u videogen /opt/videogen/venv/bin/pip install -r /opt/videogen/api/requirements.txt

# 5. Copier .env (avec vraies clés API)
sudo cp .env.production /opt/videogen/api/.env
sudo chown videogen:videogen /opt/videogen/api/.env
sudo chmod 600 /opt/videogen/api/.env

# 6. Installer et démarrer le service
sudo cp /opt/videogen/api/systemd/videogen.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable videogen
sudo systemctl start videogen

# 7. Vérifier
sudo systemctl status videogen
curl http://localhost:8000/health
```

### Step 8.2 — Vérification déploiement

```bash
# Sanity check depuis le VPS
curl -s http://localhost:8000/health | python3 -m json.tool
# Attendu : {"status": "ok", "version": "1.0.0", "environment": "production", ...}

# Test avec vraie clé
curl -s -X POST http://localhost:8000/generate \
  -H "Authorization: Bearer $(grep API_SECRET_KEY .env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"sheets_row": {"row_id": "test_deploy", "script": "'"$(python3 -c "print('Script de test déploiement. ' * 5)")"'", "format": "vertical", "strategy": "A", "duration": 90, "voice_id": "REAL_VOICE_ID", "cta": "Test"}}'
```

### Step 8.3 — Commit final

```bash
git add docs/deployment.md
git commit -m "feat: deployment docs + systemd service — Jour 4 complete"
```

---

## Résumé des tâches

| Task | Module | Tests | PRD | Durée estimée |
|------|--------|-------|-----|---------------|
| 1 | claude.py | 2 | §4.1 | 1-2h |
| 2 | elevenlabs.py | 2 | §4.2 | 1-2h |
| 3 | kling.py | 3 | §4.3 | 2-3h |
| 4 | library.py | 2 | §3 Strat.B | 2h |
| 5 | creatomate.py | 1 | §4.4 | 1-2h |
| 6 | Integration + timeout | 1 | §5.1 I2 | 1h |
| 7 | n8n workflow | Manuel | §2.1 | 2h |
| 8 | VPS deployment | Manuel | §2.2 | 1h |

**Total tests final visé : 26 passed**
