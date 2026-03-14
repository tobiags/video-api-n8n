# Enrichissement Claude + Page Review Prompts — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Améliorer la qualité des prompts Kling en enrichissant le contexte Claude (persona/ambiance) et offrir au client une page web optionnelle pour visualiser et modifier les prompts générés.

**Architecture:** Deux volets indépendants. Volet 1 : ajout de champs `persona`/`ambiance` dans SheetsRow, injection conditionnelle dans le system prompt Claude. Volet 2 : nouveau module `review.py` avec page HTML GET + endpoint POST relaunch sécurisé par HMAC, créant un nouveau job avec prompts modifiés.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, HMAC-SHA256, HTML/CSS/JS inline (même pattern que monitor_html.py)

**Spec:** `docs/superpowers/specs/2026-03-14-prompt-review-and-claude-enrichment-design.md`

---

## Chunk 1 : Volet 1 — Enrichissement Claude (persona/ambiance)

### Task 1: Ajouter persona/ambiance à SheetsRow

**Files:**
- Modify: `app/models.py:65-93` (SheetsRow)
- Test: `tests/test_models_persona.py` (nouveau)

- [ ] **Step 1: Write tests**

Create `tests/test_models_persona.py`:

```python
"""Tests for persona/ambiance fields on SheetsRow."""
import pytest
from app.models import SheetsRow


def test_sheets_row_persona_default_none():
    """persona defaults to None when not provided."""
    row = SheetsRow(
        row_id="1", script="A" * 50, voice_id="v1",
    )
    assert row.persona is None


def test_sheets_row_ambiance_default_none():
    """ambiance defaults to None when not provided."""
    row = SheetsRow(
        row_id="1", script="A" * 50, voice_id="v1",
    )
    assert row.ambiance is None


def test_sheets_row_persona_set():
    """persona accepts a string value."""
    row = SheetsRow(
        row_id="1", script="A" * 50, voice_id="v1",
        persona="femme 30 ans, mère de famille",
    )
    assert row.persona == "femme 30 ans, mère de famille"


def test_sheets_row_ambiance_set():
    """ambiance accepts a string value."""
    row = SheetsRow(
        row_id="1", script="A" * 50, voice_id="v1",
        ambiance="cinématique chaud, lumière dorée",
    )
    assert row.ambiance == "cinématique chaud, lumière dorée"


def test_sheets_row_persona_stripped():
    """persona is stripped of whitespace (strip_sheets_strings validator)."""
    row = SheetsRow(
        row_id="1", script="A" * 50, voice_id="v1",
        persona="  femme 30 ans  \r\n",
    )
    assert row.persona == "femme 30 ans"


def test_sheets_row_ambiance_stripped():
    """ambiance is stripped of whitespace."""
    row = SheetsRow(
        row_id="1", script="A" * 50, voice_id="v1",
        ambiance="  chaud  \n",
    )
    assert row.ambiance == "chaud"


def test_sheets_row_empty_string_persona_becomes_none():
    """Empty string persona is treated as None (falsy)."""
    row = SheetsRow(
        row_id="1", script="A" * 50, voice_id="v1",
        persona="",
    )
    # Empty string is valid — Claude code checks truthiness
    assert row.persona == ""
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `cd C:\Users\tobid\Downloads\CLAUDE\video-api && python -m pytest tests/test_models_persona.py -v`
Expected: FAIL — `persona` field doesn't exist

- [ ] **Step 3: Add fields to SheetsRow**

In `app/models.py`, add after `logo_url` field (line 75):

```python
    persona: str | None = Field(None, description="Description du protagoniste visuel (genre, âge, apparence)")
    ambiance: str | None = Field(None, description="Style visuel souhaité (tonalité, lumière, palette)")
```

Update the `strip_sheets_strings` validator to include the new fields:

```python
    @field_validator("voice_id", "script", "cta", "music_url", "logo_url", "persona", "ambiance", mode="before")
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `cd C:\Users\tobid\Downloads\CLAUDE\video-api && python -m pytest tests/test_models_persona.py -v`
Expected: 7 PASSED

- [ ] **Step 5: Commit**

```bash
cd C:\Users\tobid\Downloads\CLAUDE\video-api
git add app/models.py tests/test_models_persona.py
git commit -m "feat: add persona/ambiance fields to SheetsRow"
```

---

### Task 2: Enrichir le system prompt Claude

**Files:**
- Modify: `app/claude.py:24-75` (prompts) and `app/claude.py:77-178` (analyze_script signature)
- Test: `tests/test_claude_persona.py` (nouveau)

- [ ] **Step 1: Write tests**

Create `tests/test_claude_persona.py`:

```python
"""Tests for persona/ambiance injection in Claude system prompt."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import MINIMAL_ENV


@pytest.fixture
def env_vars(monkeypatch):
    for k, v in MINIMAL_ENV.items():
        monkeypatch.setenv(k, v)


@pytest.mark.asyncio
async def test_analyze_script_with_persona(env_vars):
    """When persona is provided, it appears in the system prompt."""
    from app.claude import analyze_script
    from app.config import get_settings
    from app.models import VideoFormat
    import httpx

    settings = get_settings()

    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = json.dumps({
        "total_duration": 10,
        "sections": [
            {"id": 1, "text": "Test", "start": 0, "end": 5, "duration": 5,
             "broll_prompt": "woman walking", "keywords": ["woman"], "scene_type": "ambient"},
            {"id": 2, "text": "Test2", "start": 5, "end": 10, "duration": 5,
             "broll_prompt": "woman smiling", "keywords": ["woman"], "scene_type": "ambient"},
        ],
    })

    with patch("app.claude.anthropic.AsyncAnthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create = AsyncMock(return_value=mock_response)

        async with httpx.AsyncClient() as http_client:
            result = await analyze_script(
                script="A" * 50,
                format_=VideoFormat.VERTICAL,
                duration=10,
                aspect_ratio="9:16",
                http_client=http_client,
                settings=settings,
                persona="femme 30 ans, mère de famille",
            )

        # Check persona was injected in system prompt
        call_kwargs = instance.messages.create.call_args
        system_text = call_kwargs.kwargs["system"]
        assert "femme 30 ans, mère de famille" in system_text
        assert result.total_duration == 10


@pytest.mark.asyncio
async def test_analyze_script_without_persona(env_vars):
    """When persona is None, the persona block is NOT in the system prompt."""
    from app.claude import analyze_script
    from app.config import get_settings
    from app.models import VideoFormat
    import httpx

    settings = get_settings()

    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = json.dumps({
        "total_duration": 10,
        "sections": [
            {"id": 1, "text": "Test", "start": 0, "end": 5, "duration": 5,
             "broll_prompt": "person walking", "keywords": ["person"], "scene_type": "ambient"},
            {"id": 2, "text": "Test2", "start": 5, "end": 10, "duration": 5,
             "broll_prompt": "person smiling", "keywords": ["person"], "scene_type": "ambient"},
        ],
    })

    with patch("app.claude.anthropic.AsyncAnthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create = AsyncMock(return_value=mock_response)

        async with httpx.AsyncClient() as http_client:
            result = await analyze_script(
                script="A" * 50,
                format_=VideoFormat.VERTICAL,
                duration=10,
                aspect_ratio="9:16",
                http_client=http_client,
                settings=settings,
            )

        call_kwargs = instance.messages.create.call_args
        system_text = call_kwargs.kwargs["system"]
        assert "CONTEXTE PERSONNAGE" not in system_text


@pytest.mark.asyncio
async def test_analyze_script_with_ambiance(env_vars):
    """When ambiance is provided, it appears in the system prompt."""
    from app.claude import analyze_script
    from app.config import get_settings
    from app.models import VideoFormat
    import httpx

    settings = get_settings()

    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = json.dumps({
        "total_duration": 10,
        "sections": [
            {"id": 1, "text": "Test", "start": 0, "end": 5, "duration": 5,
             "broll_prompt": "warm scene", "keywords": ["warm"], "scene_type": "ambient"},
            {"id": 2, "text": "Test2", "start": 5, "end": 10, "duration": 5,
             "broll_prompt": "golden light", "keywords": ["golden"], "scene_type": "ambient"},
        ],
    })

    with patch("app.claude.anthropic.AsyncAnthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create = AsyncMock(return_value=mock_response)

        async with httpx.AsyncClient() as http_client:
            await analyze_script(
                script="A" * 50,
                format_=VideoFormat.VERTICAL,
                duration=10,
                aspect_ratio="9:16",
                http_client=http_client,
                settings=settings,
                ambiance="cinématique chaud, lumière dorée",
            )

        call_kwargs = instance.messages.create.call_args
        system_text = call_kwargs.kwargs["system"]
        assert "cinématique chaud, lumière dorée" in system_text
        assert "AMBIANCE VISUELLE" in system_text
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `cd C:\Users\tobid\Downloads\CLAUDE\video-api && python -m pytest tests/test_claude_persona.py -v`
Expected: FAIL — `analyze_script() got an unexpected keyword argument 'persona'`

- [ ] **Step 3: Modify claude.py**

1. Add persona/ambiance blocks after `_SYSTEM_PROMPT` (as separate templates):

```python
_PERSONA_BLOCK = """
CONTEXTE PERSONNAGE (OBLIGATOIRE — applique à CHAQUE prompt) :
{persona}
→ Utilise EXACTEMENT ce profil pour CHAQUE prompt Kling : genre, âge, apparence.
→ CHAQUE broll_prompt DOIT commencer par le genre et l'âge du personnage."""

_AMBIANCE_BLOCK = """
AMBIANCE VISUELLE (applique à CHAQUE plan) :
{ambiance}
→ Applique ce style visuel à tous les plans : tonalité, lumière, palette."""
```

2. Update `analyze_script` signature — add `persona` and `ambiance` params:

```python
async def analyze_script(
    script: str,
    format_: VideoFormat,
    duration: int,
    aspect_ratio: str,
    http_client: httpx.AsyncClient,
    settings: Settings,
    persona: str | None = None,
    ambiance: str | None = None,
) -> ScriptAnalysis:
```

3. In the function body, build the system prompt conditionally (replace lines 118-122):

```python
    system = _SYSTEM_PROMPT.format(
        clip_duration=settings.KLING_DURATION,
        total_duration=duration,
        aspect_ratio=aspect_ratio,
    )
    if persona:
        system += _PERSONA_BLOCK.format(persona=persona)
    if ambiance:
        system += _AMBIANCE_BLOCK.format(ambiance=ambiance)
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `cd C:\Users\tobid\Downloads\CLAUDE\video-api && python -m pytest tests/test_claude_persona.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
cd C:\Users\tobid\Downloads\CLAUDE\video-api
git add app/claude.py tests/test_claude_persona.py
git commit -m "feat: inject persona/ambiance context into Claude system prompt"
```

---

### Task 3: Passer persona/ambiance dans le pipeline

**Files:**
- Modify: `app/main.py:548-555` (analyze_script call)

- [ ] **Step 1: Update the analyze_script call in main.py**

In `app/main.py`, update the `analyze_script()` call (around line 548) to pass persona and ambiance:

```python
                script_analysis = await analyze_script(
                    script=row.script,
                    format_=row.format,
                    duration=row.duration,
                    aspect_ratio=row.aspect_ratio,
                    http_client=http_client,
                    settings=settings,
                    persona=row.persona,
                    ambiance=row.ambiance,
                )
```

- [ ] **Step 2: Run existing tests to verify no regression**

Run: `cd C:\Users\tobid\Downloads\CLAUDE\video-api && python -m pytest tests/test_script_parser.py tests/test_claude_persona.py tests/test_models_persona.py -v`
Expected: All PASSED

- [ ] **Step 3: Commit**

```bash
cd C:\Users\tobid\Downloads\CLAUDE\video-api
git add app/main.py
git commit -m "feat: pass persona/ambiance to analyze_script in pipeline"
```

---

### Task 4: Mettre à jour le workflow n8n

**Files:**
- Modify: `C:\Users\tobid\Downloads\LANCEMENT TACHES v2.json`

- [ ] **Step 1: Update POST body in workflow**

In the `jsonBody` of the POST /generate node, add persona and ambiance fields:

```
persona: $('Filtre Statut OK').item.json['Personnage'] || '',
ambiance: $('Filtre Statut OK').item.json['Ambiance'] || ''
```

- [ ] **Step 2: Copy workflow file into repo and commit**

```bash
cd C:\Users\tobid\Downloads\CLAUDE\video-api
cp "C:\Users\tobid\Downloads\LANCEMENT TACHES v2.json" docs/n8n-workflow-v2.json
git add docs/n8n-workflow-v2.json
git commit -m "chore: add persona/ambiance to n8n workflow POST body"
```

Note: Théo doit ajouter manuellement les colonnes `Personnage` (K) et `Ambiance` (L) dans le Google Sheet. Réimporter `docs/n8n-workflow-v2.json` dans n8n.

---

## Chunk 2 : Volet 2 — Page review (models + errors)

### Task 5: Ajouter les champs review aux models

**Files:**
- Modify: `app/models.py` (ScriptAnalysis, VideoJob, NotificationPayload)
- Test: `tests/test_models_review.py` (nouveau)

- [ ] **Step 1: Write tests**

Create `tests/test_models_review.py`:

```python
"""Tests for review-related model fields."""
import pytest
from uuid import uuid4

from app.models import ScriptAnalysis, ScriptSection, VideoJob, VideoGenerationRequest, SheetsRow, NotificationPayload, NotificationType


def test_script_analysis_source_review():
    """source accepts 'review' literal."""
    sa = ScriptAnalysis(
        total_duration=10,
        sections=[
            ScriptSection(id=1, text="T", start=0, end=5, duration=5,
                          broll_prompt="test prompt here for kling", keywords=["t"], scene_type="ambient"),
            ScriptSection(id=2, text="T2", start=5, end=10, duration=5,
                          broll_prompt="test prompt two for kling", keywords=["t"], scene_type="ambient"),
        ],
        source="review",
        original_source="claude",
    )
    assert sa.source == "review"
    assert sa.original_source == "claude"


def test_script_analysis_original_source_default_none():
    """original_source defaults to None."""
    sa = ScriptAnalysis(
        total_duration=10,
        sections=[
            ScriptSection(id=1, text="T", start=0, end=5, duration=5,
                          broll_prompt="test prompt here for kling", keywords=["t"], scene_type="ambient"),
            ScriptSection(id=2, text="T2", start=5, end=10, duration=5,
                          broll_prompt="test prompt two for kling", keywords=["t"], scene_type="ambient"),
        ],
    )
    assert sa.original_source is None


def test_video_job_parent_job_id_default():
    """parent_job_id defaults to None."""
    jid = uuid4()
    req = VideoGenerationRequest(
        job_id=jid,
        sheets_row=SheetsRow(row_id="1", script="A" * 50, voice_id="v1"),
    )
    job = VideoJob(job_id=jid, row_id="1", request=req)
    assert job.parent_job_id is None
    assert job.relaunch_count == 0


def test_video_job_parent_job_id_set():
    """parent_job_id can be set to a UUID."""
    jid = uuid4()
    parent = uuid4()
    req = VideoGenerationRequest(
        job_id=jid,
        sheets_row=SheetsRow(row_id="1", script="A" * 50, voice_id="v1"),
    )
    job = VideoJob(job_id=jid, row_id="1", request=req, parent_job_id=parent, relaunch_count=1)
    assert job.parent_job_id == parent
    assert job.relaunch_count == 1


def test_video_job_review_url_default():
    """review_url defaults to None."""
    jid = uuid4()
    req = VideoGenerationRequest(
        job_id=jid,
        sheets_row=SheetsRow(row_id="1", script="A" * 50, voice_id="v1"),
    )
    job = VideoJob(job_id=jid, row_id="1", request=req)
    assert job.review_url is None


def test_notification_payload_review_url():
    """NotificationPayload accepts review_url."""
    payload = NotificationPayload(
        type=NotificationType.SUCCESS,
        job_id=uuid4(),
        row_id="1",
        message="Done",
        review_url="https://api.example.com/review/abc-123",
    )
    assert payload.review_url == "https://api.example.com/review/abc-123"
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `cd C:\Users\tobid\Downloads\CLAUDE\video-api && python -m pytest tests/test_models_review.py -v`
Expected: FAIL — fields don't exist yet

- [ ] **Step 3: Add fields to models**

1. In `ScriptAnalysis` — update `source` and add `original_source` (after the existing `source` field):

```python
    source: Literal["claude", "parser", "review"] = Field(
        "claude", description="Origine de l'analyse : Claude API, parser pré-découpé, ou review client"
    )
    original_source: Literal["claude", "parser"] | None = Field(
        None, description="Source originale avant modification review"
    )
```

2. In `VideoJob` — add after `drive_url` field:

```python
    review_url: str | None = None
    parent_job_id: UUID | None = Field(None, description="Job original si relance depuis review")
    relaunch_count: int = Field(0, description="Nombre de relances depuis ce job (max 2)")
```

3. In `NotificationPayload` — add after `corrective_action`:

```python
    review_url: str | None = Field(None, description="URL de la page review des prompts")
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `cd C:\Users\tobid\Downloads\CLAUDE\video-api && python -m pytest tests/test_models_review.py -v`
Expected: 6 PASSED

- [ ] **Step 5: Run ALL tests to check regression**

Run: `cd C:\Users\tobid\Downloads\CLAUDE\video-api && python -m pytest tests/ -v`
Expected: All PASSED (the existing `source: Literal["claude", "parser"]` tests should still pass since "claude" and "parser" are still valid)

- [ ] **Step 6: Commit**

```bash
cd C:\Users\tobid\Downloads\CLAUDE\video-api
git add app/models.py tests/test_models_review.py
git commit -m "feat: add review fields to ScriptAnalysis, VideoJob, NotificationPayload"
```

---

## Chunk 3 : Volet 2 — Page review (review.py + HTML)

### Task 6: Créer review.py avec GET /review/{job_id}

**Files:**
- Create: `app/review.py`
- Create: `app/review_html.py` (HTML template)
- Test: `tests/test_review.py` (nouveau)

- [ ] **Step 1: Write tests**

Create `tests/test_review.py`:

```python
"""Tests for review page and relaunch endpoint."""
import hmac
import hashlib
import json
import pytest
from uuid import uuid4

from tests.conftest import MINIMAL_ENV
from app.models import (
    SheetsRow, VideoGenerationRequest, VideoJob, ScriptAnalysis,
    ScriptSection, JobStatus,
)


@pytest.fixture
def env_vars(monkeypatch):
    for k, v in MINIMAL_ENV.items():
        monkeypatch.setenv(k, v)


def _make_job_with_analysis(job_id=None):
    """Helper: create a VideoJob with script_analysis populated."""
    jid = job_id or uuid4()
    req = VideoGenerationRequest(
        job_id=jid,
        sheets_row=SheetsRow(
            row_id="2", script="A" * 50, voice_id="v1",
            format="vertical", strategy="B", duration=60,
        ),
        webhook_url="https://example.com/webhook",
    )
    job = VideoJob(job_id=jid, row_id="2", request=req)
    job.script_analysis = ScriptAnalysis(
        total_duration=10,
        sections=[
            ScriptSection(id=1, text="Voix off un", start=0, end=5, duration=5,
                          broll_prompt="A woman walking in a park at sunset",
                          keywords=["woman", "park", "sunset"], scene_type="emotion"),
            ScriptSection(id=2, text="Voix off deux", start=5, end=10, duration=5,
                          broll_prompt="Close-up hands typing on laptop",
                          keywords=["hands", "laptop", "typing"], scene_type="ambient"),
        ],
        source="claude",
    )
    return job


def test_review_page_returns_html(env_vars):
    """GET /review/{job_id} returns HTML when job has script_analysis."""
    from app.main import create_app
    from app.config import get_settings
    from starlette.testclient import TestClient

    settings = get_settings()
    app = create_app(settings)

    job = _make_job_with_analysis()

    with TestClient(app) as client:
        app.state.jobs[job.job_id] = job
        resp = client.get(f"/review/{job.job_id}")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "woman walking" in resp.text
        assert "Voix off un" in resp.text


def test_review_page_job_not_found(env_vars):
    """GET /review/{job_id} returns 404 for unknown job."""
    from app.main import create_app
    from app.config import get_settings
    from starlette.testclient import TestClient

    settings = get_settings()
    app = create_app(settings)

    with TestClient(app) as client:
        resp = client.get(f"/review/{uuid4()}")
        assert resp.status_code == 404


def test_review_page_waiting(env_vars):
    """GET /review/{job_id} returns waiting page when script_analysis not ready."""
    from app.main import create_app
    from app.config import get_settings
    from starlette.testclient import TestClient

    settings = get_settings()
    app = create_app(settings)

    jid = uuid4()
    req = VideoGenerationRequest(
        job_id=jid,
        sheets_row=SheetsRow(row_id="2", script="A" * 50, voice_id="v1"),
    )
    job = VideoJob(job_id=jid, row_id="2", request=req)
    # script_analysis is None

    with TestClient(app) as client:
        app.state.jobs[jid] = job
        resp = client.get(f"/review/{jid}")
        assert resp.status_code == 200
        assert "Analyse en cours" in resp.text


def test_relaunch_creates_new_job(env_vars):
    """POST /review/{job_id}/relaunch creates a new job with modified prompts."""
    from app.main import create_app
    from app.config import get_settings
    from starlette.testclient import TestClient
    from unittest.mock import patch, AsyncMock

    settings = get_settings()
    app = create_app(settings)
    job = _make_job_with_analysis()

    # Generate valid HMAC token
    token = hmac.new(
        settings.api_secret_key.encode(),
        str(job.job_id).encode(),
        hashlib.sha256,
    ).hexdigest()

    with TestClient(app) as client:
        app.state.jobs[job.job_id] = job

        with patch("app.review.run_pipeline") as mock_run_pipeline:
            resp = client.post(
                f"/review/{job.job_id}/relaunch?token={token}",
                json={
                    "sections": [
                        {"id": 1, "broll_prompt": "Modified prompt one here",
                         "keywords": ["modified"], "scene_type": "emotion"},
                        {"id": 2, "broll_prompt": "Modified prompt two here",
                         "keywords": ["changed"], "scene_type": "ambient"},
                    ]
                },
            )

        assert resp.status_code == 201
        # Verify pipeline was launched
        mock_run_pipeline.assert_called_once()
        data = resp.json()
        assert "job_id" in data
        new_job_id = data["job_id"]
        assert new_job_id != str(job.job_id)

        # Verify new job exists with modified prompts
        from uuid import UUID
        new_job = app.state.jobs[UUID(new_job_id)]
        assert new_job.parent_job_id == job.job_id
        assert new_job.script_analysis.source == "review"
        assert new_job.script_analysis.original_source == "claude"
        assert new_job.script_analysis.sections[0].broll_prompt == "Modified prompt one here"
        # Original text preserved
        assert new_job.script_analysis.sections[0].text == "Voix off un"


def test_relaunch_invalid_token(env_vars):
    """POST with invalid HMAC token returns 403."""
    from app.main import create_app
    from app.config import get_settings
    from starlette.testclient import TestClient

    settings = get_settings()
    app = create_app(settings)
    job = _make_job_with_analysis()

    with TestClient(app) as client:
        app.state.jobs[job.job_id] = job
        resp = client.post(
            f"/review/{job.job_id}/relaunch?token=invalid",
            json={"sections": []},
        )
        assert resp.status_code == 403


def test_relaunch_max_count(env_vars):
    """POST relaunch beyond max 2 returns 429."""
    from app.main import create_app
    from app.config import get_settings
    from starlette.testclient import TestClient

    settings = get_settings()
    app = create_app(settings)
    job = _make_job_with_analysis()
    job.relaunch_count = 2  # Already at max

    token = hmac.new(
        settings.api_secret_key.encode(),
        str(job.job_id).encode(),
        hashlib.sha256,
    ).hexdigest()

    with TestClient(app) as client:
        app.state.jobs[job.job_id] = job
        resp = client.post(
            f"/review/{job.job_id}/relaunch?token={token}",
            json={"sections": [
                {"id": 1, "broll_prompt": "test prompt modified", "keywords": ["t"], "scene_type": "ambient"},
                {"id": 2, "broll_prompt": "test prompt two mod", "keywords": ["t"], "scene_type": "ambient"},
            ]},
        )
        assert resp.status_code == 429


def test_relaunch_empty_sections_rejected(env_vars):
    """POST with empty sections list returns 422 (min_length=1)."""
    from app.main import create_app
    from app.config import get_settings
    from starlette.testclient import TestClient

    settings = get_settings()
    app = create_app(settings)
    job = _make_job_with_analysis()

    token = hmac.new(
        settings.api_secret_key.encode(),
        str(job.job_id).encode(),
        hashlib.sha256,
    ).hexdigest()

    with TestClient(app) as client:
        app.state.jobs[job.job_id] = job
        resp = client.post(
            f"/review/{job.job_id}/relaunch?token={token}",
            json={"sections": []},
        )
        assert resp.status_code == 422
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `cd C:\Users\tobid\Downloads\CLAUDE\video-api && python -m pytest tests/test_review.py -v`
Expected: FAIL — module `app.review` doesn't exist

- [ ] **Step 3: Create review_html.py**

Create `app/review_html.py` with two string constants:

1. `REVIEW_WAITING_HTML` — waiting page shown when `script_analysis` is None:
   - "Analyse en cours..." message with auto-refresh every 3s (JS polling `GET /status/{job_id}`)
   - Placeholders: `{job_id}`, `{job_id_short}`

2. `REVIEW_HTML` — main review page:
   - Responsive page matching monitor style
   - Editable textareas for prompts/keywords
   - HMAC token in hidden form field
   - Debounce on relaunch button
   - Pipeline status badge with live polling
   - Warning when relaunching during active pipeline
   - Placeholders: `{job_id_short}`, `{job_id}`, `{sections_json}`, `{script_text}`, `{status}`, `{token}`, `{api_base}`, `{source}`, `{total_duration}`, `{drive_url}`

- [ ] **Step 4: Create review.py**

Create `app/review.py` with:

```python
"""
review.py — Page de review des prompts Kling (optionnelle, non-bloquante).

Endpoints :
  GET  /review/{job_id}           — Page HTML lecture/édition des prompts
  POST /review/{job_id}/relaunch  — Relance pipeline avec prompts modifiés
"""
import hashlib
import hmac as hmac_mod
import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from app.config import get_settings
from app.models import (
    JobStatus,
    SceneType,
    ScriptAnalysis,
    ScriptSection,
    VideoGenerationRequest,
    VideoJob,
)
from app.review_html import REVIEW_HTML, REVIEW_WAITING_HTML

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Review"])


class RelaunchSection(BaseModel):
    id: int
    broll_prompt: str
    keywords: list[str]
    scene_type: SceneType


class RelaunchRequest(BaseModel):
    sections: list[RelaunchSection] = Field(..., min_length=1)


def _generate_token(job_id: UUID, secret: str) -> str:
    return hmac_mod.new(secret.encode(), str(job_id).encode(), hashlib.sha256).hexdigest()


def _verify_token(job_id: UUID, token: str, secret: str) -> bool:
    expected = _generate_token(job_id, secret)
    return hmac_mod.compare_digest(token, expected)


@router.get("/review/{job_id}", response_class=HTMLResponse)
async def review_page(job_id: UUID, request: Request):
    """Page de review des prompts — accessible sans auth (UUID = token)."""
    jobs: dict = request.app.state.jobs
    job = jobs.get(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job non trouvé ou expiré")

    if job.script_analysis is None:
        # Pipeline encore à l'étape Claude — page d'attente auto-refresh
        return HTMLResponse(
            REVIEW_WAITING_HTML.format(
                job_id=str(job_id),
                job_id_short=str(job_id)[:8],
            )
        )

    settings = get_settings()
    token = _generate_token(job_id, settings.api_secret_key)

    import json
    sections_json = json.dumps(
        [s.model_dump(mode="json") for s in job.script_analysis.sections],
        ensure_ascii=False,
    )

    return HTMLResponse(
        REVIEW_HTML.format(
            job_id=str(job_id),
            job_id_short=str(job_id)[:8],
            sections_json=sections_json,
            script_text=job.request.sheets_row.script[:500],
            status=job.status.value,
            token=token,
            api_base="",
            source=job.script_analysis.source,
            total_duration=job.script_analysis.total_duration,
            drive_url=job.drive_url or "",
        )
    )


@router.post("/review/{job_id}/relaunch", status_code=201)
async def relaunch_with_modifications(
    job_id: UUID,
    body: RelaunchRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    token: str = Query(...),
):
    """Relance le pipeline avec les prompts modifiés par le client."""
    settings = get_settings()

    # Verify HMAC token
    if not _verify_token(job_id, token, settings.api_secret_key):
        raise HTTPException(status_code=403, detail="Token invalide")

    jobs: dict = request.app.state.jobs
    original_job = jobs.get(job_id)

    if original_job is None:
        raise HTTPException(
            status_code=410,
            detail="Job original expiré (redémarrage serveur). Relancez depuis Google Sheets.",
        )

    if original_job.script_analysis is None:
        raise HTTPException(status_code=400, detail="Analyse pas encore disponible")

    # Check relaunch limit
    if original_job.relaunch_count >= 2:
        raise HTTPException(
            status_code=429,
            detail="Maximum 2 relances par job atteint",
        )

    # Build modified ScriptAnalysis
    original_sections = original_job.script_analysis.sections
    section_map = {s.id: s for s in original_sections}

    modified_sections = []
    for mod in body.sections:
        orig = section_map.get(mod.id)
        if orig is None:
            raise HTTPException(status_code=400, detail=f"Section {mod.id} introuvable")
        modified_sections.append(
            ScriptSection(
                id=orig.id,
                text=orig.text,
                start=orig.start,
                end=orig.end,
                duration=orig.duration,
                broll_prompt=mod.broll_prompt,
                keywords=mod.keywords,
                scene_type=mod.scene_type,
            )
        )

    modified_analysis = ScriptAnalysis(
        total_duration=original_job.script_analysis.total_duration,
        sections=modified_sections,
        source="review",
        original_source=original_job.script_analysis.source
            if original_job.script_analysis.source != "review"
            else original_job.script_analysis.original_source,
    )

    # Create new job
    new_job_id = uuid4()
    row = original_job.request.sheets_row
    new_request = VideoGenerationRequest(
        job_id=new_job_id,
        sheets_row=row,
        webhook_url=original_job.request.webhook_url,
    )
    new_job = VideoJob(
        job_id=new_job_id,
        row_id=row.row_id,
        request=new_request,
        parent_job_id=job_id,
        script_analysis=modified_analysis,
    )

    # Store new job and increment relaunch count on original
    jobs[new_job_id] = new_job
    original_job.relaunch_count += 1

    # Launch pipeline from ElevenLabs (bypass Claude)
    from app.main import run_pipeline
    background_tasks.add_task(run_pipeline, job_id=new_job_id, app=request.app, settings=settings)

    logger.info(
        "Relaunch %s → %s (parent: %s, relaunch #%d)",
        job_id, new_job_id, job_id, original_job.relaunch_count,
    )

    return JSONResponse(
        status_code=201,
        content={
            "job_id": str(new_job_id),
            "parent_job_id": str(job_id),
            "review_url": f"/review/{new_job_id}",
            "message": "Nouveau pipeline lancé avec vos modifications",
        },
    )
```

- [ ] **Step 5: Add pipeline bypass for relaunch jobs in main.py**

In `app/main.py`, update the script analysis routing in `run_pipeline` to check `job.script_analysis` FIRST (before pre-formatted or Claude):

```python
            if job.script_analysis is not None:
                # Relaunch depuis review — script_analysis déjà fourni
                logger.info("Job %s | Script analysis fourni (review/relaunch), bypass Claude", job_id)
                script_analysis = job.script_analysis
                _update_job_progress(
                    job, JobStatus.RUNNING_ELEVENLABS,
                    "Prompts modifiés par le client (bypass Claude)", 15,
                    f"{script_analysis.section_count} plans",
                )
            elif detect_preformatted(row.script):
```

This ensures relaunched jobs skip both Claude and the parser since `script_analysis` is already populated.

- [ ] **Step 6: Register the router in main.py**

In `app/main.py`, add import:
```python
from app.review import router as review_router
```

In `create_app()`, after the existing route registrations, add:
```python
    app.include_router(review_router)
```

- [ ] **Step 7: Run tests — expect PASS**

Run: `cd C:\Users\tobid\Downloads\CLAUDE\video-api && python -m pytest tests/test_review.py -v`
Expected: 7 PASSED

- [ ] **Step 8: Run ALL tests**

Run: `cd C:\Users\tobid\Downloads\CLAUDE\video-api && python -m pytest tests/ -v`
Expected: All PASSED

- [ ] **Step 9: Commit**

```bash
cd C:\Users\tobid\Downloads\CLAUDE\video-api
git add app/review.py app/review_html.py app/main.py tests/test_review.py
git commit -m "feat: add review page with GET view and POST relaunch endpoints"
```

---

## Chunk 4 : Intégration pipeline + review_url

### Task 7: Générer review_url dans le pipeline et l'inclure dans les notifications

**Files:**
- Modify: `app/main.py` (après étape Claude, dans notification success)

- [ ] **Step 1: Add review_url generation after script analysis**

In `app/main.py`, after `job.script_analysis = script_analysis` and the logger.info line, add:

```python
            # Générer le lien review
            base = settings.API_BASE_URL or str(request.base_url).rstrip("/") if hasattr(request, 'base_url') else ""
            job.review_url = f"{base}/review/{job_id}" if base else f"/review/{job_id}"
```

Note: `run_pipeline` doesn't have access to `request`. Use `settings.API_BASE_URL` directly:

```python
            job.review_url = f"{settings.API_BASE_URL}/review/{job_id}"
```

- [ ] **Step 2: Include review_url in success notification**

Find the success notification (where `NotificationPayload` with `type=SUCCESS` is created) and add `review_url=job.review_url`.

- [ ] **Step 3: Run all tests**

Run: `cd C:\Users\tobid\Downloads\CLAUDE\video-api && python -m pytest tests/ -v`
Expected: All PASSED

- [ ] **Step 4: Commit**

```bash
cd C:\Users\tobid\Downloads\CLAUDE\video-api
git add app/main.py
git commit -m "feat: generate review_url and include in webhook notifications"
```

---

### Task 8: Push et déployer

- [ ] **Step 1: Run full test suite one final time**

Run: `cd C:\Users\tobid\Downloads\CLAUDE\video-api && python -m pytest tests/ -v`

- [ ] **Step 2: Push**

```bash
cd C:\Users\tobid\Downloads\CLAUDE\video-api
git push origin master
```

- [ ] **Step 3: Reimport workflow n8n**

Reimporter `LANCEMENT TACHES v2.json` dans n8n avec les champs persona/ambiance.

- [ ] **Step 4: Ajouter colonnes Google Sheet**

Théo ajoute manuellement : colonne K = `Personnage`, colonne L = `Ambiance`.

- [ ] **Step 5: Test end-to-end**

1. Remplir une ligne dans le Sheet avec persona rempli (ex: "femme 30 ans, mère fatiguée")
2. Mettre statut à "ok"
3. Vérifier dans les logs que le system prompt contient bien le persona
4. Vérifier que la page `/review/{job_id}` s'affiche correctement
5. Tester la modification et le relaunch
