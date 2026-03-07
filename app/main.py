"""
main.py — Point d'entrée FastAPI + orchestrateur pipeline (PRD §2.1)

Architecture :
  - Lifespan : init httpx client partagé + job store in-memory
  - Sécurité : validation secret partagé n8n ↔ FastAPI (header Bearer)
  - POST /generate    → démarre job en background, retourne job_id immédiatement
  - GET  /status/{id} → polling statut par n8n ou client
  - GET  /health      → health check pour systemd / monitoring

Orchestrateur (run_pipeline) :
  Claude → ElevenLabs → Clips (Kling/Library/Pexels) → Creatomate → notification n8n

NOTE Jour 2 : remplacer app.state.jobs par Redis pour supporter
plusieurs workers Gunicorn et la persistance après redémarrage.
"""
import asyncio
import hmac
import logging
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.config import Settings, get_settings
from app.errors import AuthenticationError, JobNotFoundError, register_exception_handlers
from app.models import (
    ErrorResponse,
    GenerationStrategy,
    HealthResponse,
    JobCreatedResponse,
    JobProgress,
    JobStatus,
    JobStatusResponse,
    NotificationPayload,
    NotificationType,
    VideoGenerationRequest,
    VideoJob,
)

# Imports stubs — implémentés aux Jours 2 & 3
from app.claude import analyze_script
from app.elevenlabs import generate_voiceover
from app.kling import generate_clips
from app.library import select_library_clips
from app.creatomate import assemble_video

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════════════════════

def _setup_logging(debug: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Réduire le bruit des libs externes
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


# ══════════════════════════════════════════════════════════════════════════════
# LIFESPAN — Startup / Shutdown
# ══════════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    _setup_logging(settings.DEBUG)

    logger.info(
        "Démarrage %s v%s [%s]", settings.APP_NAME, settings.APP_VERSION, settings.ENVIRONMENT
    )

    # ── Client HTTP partagé (toutes les APIs externes) ────────────────────────
    # Un seul client pour tout le process = pool de connexions efficace.
    app.state.http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            settings.HTTP_TIMEOUT_DEFAULT,
            connect=10.0,
            pool=5.0,
        ),
        limits=httpx.Limits(
            max_connections=settings.HTTP_MAX_CONNECTIONS,
            max_keepalive_connections=settings.HTTP_MAX_KEEPALIVE,
        ),
        http2=True,
        follow_redirects=True,
    )

    # ── Job store in-memory (remplacé par Redis au Jour 2) ────────────────────
    app.state.jobs: dict[UUID, VideoJob] = {}

    logger.info("Client HTTP initialisé. API prête à recevoir les requêtes n8n.")
    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    await app.state.http_client.aclose()
    running = sum(
        1 for j in app.state.jobs.values()
        if j.status not in (JobStatus.COMPLETED, JobStatus.FAILED)
    )
    if running:
        logger.warning("%d job(s) encore en cours à l'arrêt du serveur.", running)
    logger.info("Client HTTP fermé. Arrêt propre.")


# ══════════════════════════════════════════════════════════════════════════════
# APP FACTORY
# ══════════════════════════════════════════════════════════════════════════════

def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = get_settings()

    # ── Sentry (optionnel — activé seulement si SENTRY_DSN est défini) ───────
    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            integrations=[StarletteIntegration(), FastApiIntegration()],
            environment=settings.ENVIRONMENT,
            release=settings.APP_VERSION,
            traces_sample_rate=0.1,   # 10% des requêtes → performance monitoring
            send_default_pii=False,   # RGPD : pas de données perso dans les traces
        )
        logging.getLogger(__name__).info("Sentry initialisé [%s]", settings.ENVIRONMENT)

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "API d'orchestration pour la génération automatique de pubs vidéo. "
            "Déclenché par n8n sur statut Google Sheets = OK."
        ),
        # Désactiver la doc en production (pas d'exposition publique)
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
        responses={
            401: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
        },
    )

    # ── Middleware ────────────────────────────────────────────────────────────
    # CORS : n8n tourne en localhost sur le même VPS — pas de CORS nécessaire
    # mais on l'ajoute pour les tests depuis dev local.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5678", "http://127.0.0.1:5678"],  # n8n local
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    if settings.is_production:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.TRUSTED_HOSTS)

    # ── Middleware de logging des requêtes ────────────────────────────────────
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = (time.monotonic() - start) * 1000
        logger.info(
            "%s %s → %d (%.0fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

    # ── Exception handlers ────────────────────────────────────────────────────
    register_exception_handlers(app)

    # ── Routes ───────────────────────────────────────────────────────────────
    app.include_router(_build_router())

    return app


# ══════════════════════════════════════════════════════════════════════════════
# DÉPENDANCES
# ══════════════════════════════════════════════════════════════════════════════

def _verify_api_key(
    authorization: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    """
    Valide le secret partagé entre n8n et FastAPI.
    n8n doit envoyer : Authorization: Bearer <API_SECRET_KEY>
    """
    if not authorization:
        raise AuthenticationError("Header Authorization manquant")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token, settings.api_secret_key):
        raise AuthenticationError("Token API invalide")


SecureEndpoint = Annotated[None, Depends(_verify_api_key)]


def _get_job(job_id: UUID, request: Request) -> VideoJob:
    """Récupère un job du store ou lève 404."""
    job = request.app.state.jobs.get(job_id)
    if not job:
        raise JobNotFoundError(f"Job {job_id} introuvable", job_id=job_id)
    return job


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

def _build_router():
    from fastapi import APIRouter
    router = APIRouter()

    # ── Health ────────────────────────────────────────────────────────────────
    @router.get(
        "/health",
        response_model=HealthResponse,
        summary="Health check",
        tags=["Infrastructure"],
    )
    async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
        return HealthResponse(
            status="ok",
            version=settings.APP_VERSION,
            environment=settings.ENVIRONMENT,
        )

    # ── Démarrer une génération ───────────────────────────────────────────────
    @router.post(
        "/generate",
        response_model=JobCreatedResponse,
        status_code=status.HTTP_202_ACCEPTED,
        summary="Lancer la génération d'une pub vidéo",
        description=(
            "Reçoit les données d'une ligne Google Sheets (statut=OK) depuis n8n. "
            "Démarre le pipeline en background et retourne immédiatement un job_id. "
            "Le résultat final est envoyé au webhook_url fourni."
        ),
        tags=["Génération"],
    )
    async def generate_video(
        payload: VideoGenerationRequest,
        background_tasks: BackgroundTasks,
        request: Request,
        _: SecureEndpoint,
        settings: Settings = Depends(get_settings),
    ) -> JobCreatedResponse:
        job = VideoJob(
            job_id=payload.job_id,
            row_id=payload.sheets_row.row_id,
            request=payload,
        )
        request.app.state.jobs[payload.job_id] = job

        background_tasks.add_task(
            run_pipeline,
            job_id=payload.job_id,
            app=request.app,
            settings=settings,
        )

        logger.info(
            "Job %s créé | row=%s | strategy=%s | format=%s | duration=%ds",
            payload.job_id,
            payload.sheets_row.row_id,
            payload.sheets_row.strategy.value,
            payload.sheets_row.format.value,
            payload.sheets_row.duration,
        )

        return JobCreatedResponse(
            job_id=payload.job_id,
            status=JobStatus.PENDING,
            message="Job créé. Pipeline démarré en arrière-plan.",
            status_url=f"{request.base_url}status/{payload.job_id}",
        )

    # ── Statut d'un job ───────────────────────────────────────────────────────
    @router.get(
        "/status/{job_id}",
        response_model=JobStatusResponse,
        summary="Statut d'un job de génération",
        tags=["Génération"],
    )
    async def get_status(
        job_id: UUID,
        request: Request,
        _: SecureEndpoint,
    ) -> JobStatusResponse:
        job = _get_job(job_id, request)
        return JobStatusResponse(
            job_id=job.job_id,
            row_id=job.row_id,
            status=job.status,
            progress=job.progress,
            drive_url=job.drive_url,
            error=job.error,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    return router


# ══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATEUR PIPELINE (background task)
# ══════════════════════════════════════════════════════════════════════════════

def _update_job_progress(
    job: VideoJob,
    status: JobStatus,
    step: str,
    percentage: int,
    detail: str = "",
    clips_done: int | None = None,
    clips_total: int | None = None,
) -> None:
    """Met à jour le statut du job en mémoire (thread-safe pour asyncio)."""
    job.status = status
    job.progress = JobProgress(
        status=status,
        step=step,
        percentage=percentage,
        detail=detail,
        clips_done=clips_done,
        clips_total=clips_total,
    )
    job.updated_at = datetime.now(UTC)
    logger.info(
        "Job %s | %d%% | %s | %s",
        job.job_id,
        percentage,
        step,
        detail or "",
    )


async def _notify_n8n(
    webhook_url: str,
    payload: NotificationPayload,
    http_client: httpx.AsyncClient,
) -> None:
    """Envoie une notification au webhook n8n. Silencieux en cas d'échec."""
    try:
        resp = await http_client.post(
            webhook_url,
            json=payload.model_dump(mode="json"),
            timeout=10.0,
        )
        resp.raise_for_status()
        logger.info("Notification n8n envoyée [%s] → %s", payload.type.value, webhook_url)
    except Exception as e:
        logger.error("Échec notification n8n [%s]: %s", payload.type.value, e)


async def run_pipeline(
    job_id: UUID,
    app: FastAPI,
    settings: Settings,
) -> None:
    """
    Orchestrateur complet du pipeline de génération vidéo (PRD §2.1).

    Étapes :
      1. Claude  → découpage script + prompts B-roll (PRD §4.1)
      2. ElevenLabs → voix off + timestamps (PRD §4.2)
      3. Clips   → Kling / Library / Pexels selon stratégie (PRD §4.3 + §3)
      4. Creatomate → assemblage MP4 final (PRD §4.4)
      5. Notification n8n → upload Drive + mise à jour Sheets (PRD §5.2)
    """
    job: VideoJob = app.state.jobs[job_id]
    http_client: httpx.AsyncClient = app.state.http_client
    request = job.request
    row = request.sheets_row

    try:
        async with asyncio.timeout(settings.HTTP_TIMEOUT_VIDEO_GEN):  # global guard — I2 resolved
            # ── Étape 1 : Analyse script (Claude) ─────────────────────────────────
            _update_job_progress(
                job, JobStatus.RUNNING_CLAUDE,
                "Analyse du script avec Claude", 10,
                f"Découpage en sections de ~{settings.KLING_DURATION}s",
            )
            script_analysis = await analyze_script(
                script=row.script,
                format_=row.format,
                duration=row.duration,
                aspect_ratio=row.aspect_ratio,
                http_client=http_client,
                settings=settings,
            )
            job.script_analysis = script_analysis
            logger.info(
                "Job %s | Claude OK : %d sections, durée totale %ds",
                job_id, script_analysis.section_count, script_analysis.total_duration,
            )

            # ── Étape 2 : Voix off (ElevenLabs) ──────────────────────────────────
            _update_job_progress(
                job, JobStatus.RUNNING_ELEVENLABS,
                "Génération de la voix off", 25,
                f"Clone vocal {row.voice_id}",
            )
            elevenlabs_result = await generate_voiceover(
                script=row.script,
                voice_id=row.voice_id,
                http_client=http_client,
                settings=settings,
            )
            job.elevenlabs_result = elevenlabs_result
            logger.info(
                "Job %s | ElevenLabs OK : durée audio %.1fs | %d mots timestampés",
                job_id,
                elevenlabs_result.audio_duration_seconds,
                len(elevenlabs_result.timestamps),
            )

            # ── Étape 3 : Clips vidéo ─────────────────────────────────────────────
            _update_job_progress(
                job, JobStatus.RUNNING_CLIPS,
                "Génération des clips vidéo", 40,
                f"Stratégie {row.strategy.value} | {script_analysis.section_count} clips",
                clips_done=0,
                clips_total=script_analysis.section_count,
            )

            if row.strategy == GenerationStrategy.A:
                # Stratégie A : Kling pur — 100% IA générative (PRD §3)
                clips = await generate_clips(
                    sections=script_analysis.sections,
                    format_=row.format,
                    http_client=http_client,
                    settings=settings,
                    progress_callback=lambda done, total: _update_job_progress(
                        job, JobStatus.RUNNING_CLIPS,
                        "Génération Kling en cours", 40 + int(30 * done / total),
                        clips_done=done, clips_total=total,
                    ),
                )
            else:
                # Stratégie B : Library → Pexels → Kling (PRD §3)
                clips = await select_library_clips(
                    sections=script_analysis.sections,
                    format_=row.format,
                    http_client=http_client,
                    settings=settings,
                    progress_callback=lambda done, total: _update_job_progress(
                        job, JobStatus.RUNNING_CLIPS,
                        "Sélection clips (Library/Pexels/Kling)", 40 + int(30 * done / total),
                        clips_done=done, clips_total=total,
                    ),
                )

            job.clips = clips
            logger.info("Job %s | Clips OK : %d clips récupérés", job_id, len(clips))

            # ── Étape 4 : Assemblage Creatomate ───────────────────────────────────
            _update_job_progress(
                job, JobStatus.RUNNING_CREATOMATE,
                "Assemblage final de la vidéo", 75,
                "Sync voix/clips/sous-titres via Creatomate",
            )
            render_result = await assemble_video(
                script_analysis=script_analysis,
                elevenlabs_result=elevenlabs_result,
                clips=clips,
                row=row,
                http_client=http_client,
                settings=settings,
            )
            job.render_result = render_result
            logger.info(
                "Job %s | Creatomate OK : render_id=%s | url=%s",
                job_id, render_result.render_id, render_result.video_url,
            )

            # ── Étape 5 : Notification n8n (Drive upload + Sheets update) ─────────
            _update_job_progress(
                job, JobStatus.UPLOADING,
                "Notification n8n — upload Drive et mise à jour Sheets", 95,
            )

            # n8n reçoit l'URL Creatomate, upload sur Drive, met à jour Sheets
            if request.webhook_url:
                await _notify_n8n(
                    request.webhook_url,
                    NotificationPayload(
                        type=NotificationType.SUCCESS,
                        job_id=job_id,
                        row_id=row.row_id,
                        message=f"Pub générée avec succès — durée {render_result.duration_seconds:.0f}s",
                        drive_url=render_result.video_url,
                    ),
                    http_client,
                )

            # ── Terminé ───────────────────────────────────────────────────────────
            job.status = JobStatus.COMPLETED
            job.drive_url = render_result.video_url  # mis à jour après upload par n8n
            _update_job_progress(job, JobStatus.COMPLETED, "Terminé", 100)

    except asyncio.TimeoutError:
        detail = f"Pipeline timeout après {settings.HTTP_TIMEOUT_VIDEO_GEN}s"
        logger.error("Pipeline timeout job_id=%s", job_id)
        job.error = detail
        _update_job_progress(
            job, JobStatus.FAILED, "Timeout pipeline", job.progress.percentage, detail
        )
        if request.webhook_url:
            await _notify_n8n(
                request.webhook_url,
                NotificationPayload(
                    type=NotificationType.BLOCKING_ERROR,
                    job_id=job_id,
                    row_id=row.row_id,
                    message="Timeout global du pipeline",
                    error_detail=detail,
                    affected_step=job.progress.step,
                ),
                http_client,
            )

    except Exception as exc:
        logger.exception("Job %s FAILED : %s", job_id, exc)
        job.status = JobStatus.FAILED
        job.error = str(exc)
        _update_job_progress(
            job, JobStatus.FAILED, "Erreur pipeline", job.progress.percentage, str(exc)
        )

        if request.webhook_url:
            await _notify_n8n(
                request.webhook_url,
                NotificationPayload(
                    type=NotificationType.BLOCKING_ERROR,
                    job_id=job_id,
                    row_id=row.row_id,
                    message="Erreur bloquante dans le pipeline",
                    error_detail=str(exc),
                    affected_step=job.progress.step,
                ),
                http_client,
            )


# ══════════════════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE
# ══════════════════════════════════════════════════════════════════════════════

app = create_app()

if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=not settings.is_production,
        log_level="debug" if settings.DEBUG else "info",
    )
