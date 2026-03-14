"""
review.py — Page de review des prompts Kling (optionnelle, non-bloquante).

Endpoints :
  GET  /review/{job_id}           — Page HTML lecture/édition des prompts
  POST /review/{job_id}/relaunch  — Relance pipeline avec prompts modifiés
"""
import hashlib
import hmac as hmac_mod
import json
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
