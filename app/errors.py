"""
errors.py — Gestion centralisée des erreurs VideoGen (PRD §5)

Contient :
  1. Exceptions personnalisées (une par API/module)
  2. Handlers FastAPI (enregistrés dans main.py via register_exception_handlers)
  3. Helpers de construction de réponses d'erreur
  4. Logique de notification d'erreur vers n8n (PRD §5.2)
"""
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# BASE EXCEPTION
# ══════════════════════════════════════════════════════════════════════════════

class VideoGenException(Exception):
    """Exception de base pour toute l'application VideoGen."""
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        detail: str,
        job_id: UUID | None = None,
        extra: Any = None,
    ) -> None:
        self.detail = detail
        self.job_id = job_id
        self.extra = extra
        super().__init__(detail)


# ══════════════════════════════════════════════════════════════════════════════
# EXCEPTIONS — Sécurité / Auth
# ══════════════════════════════════════════════════════════════════════════════

class AuthenticationError(VideoGenException):
    """Secret API n8n ↔ FastAPI invalide ou manquant."""
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "AUTHENTICATION_ERROR"


# ══════════════════════════════════════════════════════════════════════════════
# EXCEPTIONS — Validation
# ══════════════════════════════════════════════════════════════════════════════

class RequestValidationError_(VideoGenException):
    """Payload n8n → FastAPI malformé (distinct de pydantic RequestValidationError)."""
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    error_code = "VALIDATION_ERROR"


class JobNotFoundError(VideoGenException):
    """Job ID introuvable dans le store."""
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "JOB_NOT_FOUND"


# ══════════════════════════════════════════════════════════════════════════════
# EXCEPTIONS — Modules API externes (PRD §5.1 matrice des erreurs)
# ══════════════════════════════════════════════════════════════════════════════

class ClaudeAPIError(VideoGenException):
    """
    Erreur module Claude.
    Comportement : relance avec contexte d'erreur inclus (PRD §5.1).
    """
    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "CLAUDE_API_ERROR"


class ClaudeInvalidJSONError(ClaudeAPIError):
    """Claude a retourné un JSON invalide après N tentatives."""
    error_code = "CLAUDE_INVALID_JSON"


class ElevenLabsAPIError(VideoGenException):
    """
    Erreur module ElevenLabs.
    Comportement : retry x2 avec backoff exponentiel (PRD §5.1).
    """
    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "ELEVENLABS_API_ERROR"


class ElevenLabsTimeoutError(ElevenLabsAPIError):
    """Timeout ElevenLabs — max ~5min de délai (PRD §5.1)."""
    error_code = "ELEVENLABS_TIMEOUT"


class KlingAPIError(VideoGenException):
    """
    Erreur module Kling.
    Comportement : retry auto x3, puis fallback Pexels (PRD §4.3 + §5.1).
    """
    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "KLING_API_ERROR"


class KlingClipTimeoutError(KlingAPIError):
    """Clip Kling bloqué > 10 min. Fallback Pexels déclenché automatiquement."""
    error_code = "KLING_CLIP_TIMEOUT"


class KlingUnavailableError(KlingAPIError):
    """API Kling indisponible — notification immédiate + mise en file (PRD §5.1)."""
    error_code = "KLING_UNAVAILABLE"
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE


class KlingMaxRetriesError(KlingAPIError):
    """Clip irrémédiablement raté après 3 tentatives — remplacement Pexels."""
    error_code = "KLING_MAX_RETRIES"


class PexelsAPIError(VideoGenException):
    """Erreur module Pexels (fallback Stratégie A/B)."""
    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "PEXELS_API_ERROR"


class CreatomateAPIError(VideoGenException):
    """
    Erreur module Creatomate.
    Comportement : retry x2, notification si persistant (PRD §5.1).
    """
    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "CREATOMATE_API_ERROR"


class CreatomateRenderTimeoutError(CreatomateAPIError):
    """Rendu Creatomate > 15 min."""
    error_code = "CREATOMATE_RENDER_TIMEOUT"


class GoogleAPIError(VideoGenException):
    """Erreur Google Drive ou Sheets."""
    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "GOOGLE_API_ERROR"


# ══════════════════════════════════════════════════════════════════════════════
# EXCEPTIONS — Infrastructure
# ══════════════════════════════════════════════════════════════════════════════

class JobTimeoutError(VideoGenException):
    """Timeout global du job (garde-fou final)."""
    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    error_code = "JOB_TIMEOUT"


class LibraryError(VideoGenException):
    """Erreur lecture/écriture bibliothèque clips locale (Stratégie B)."""
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code = "LIBRARY_ERROR"


# ══════════════════════════════════════════════════════════════════════════════
# HELPER — Construction réponse d'erreur JSON standardisée
# ══════════════════════════════════════════════════════════════════════════════

def _build_error_response(
    error: str,
    error_code: str,
    status_code: int,
    detail: Any = None,
    job_id: UUID | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": error,
            "error_code": error_code,
            "detail": detail,
            "job_id": str(job_id) if job_id else None,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


# ══════════════════════════════════════════════════════════════════════════════
# HANDLERS — Enregistrement dans FastAPI (appelé depuis main.py)
# ══════════════════════════════════════════════════════════════════════════════

def register_exception_handlers(app: FastAPI) -> None:
    """
    Attache tous les exception handlers à l'app FastAPI.
    À appeler UNE SEULE FOIS depuis la factory create_app().
    """

    @app.exception_handler(VideoGenException)
    async def videogen_exception_handler(
        request: Request, exc: VideoGenException
    ) -> JSONResponse:
        logger.error(
            "[%s] %s | job_id=%s | path=%s",
            exc.error_code,
            exc.detail,
            exc.job_id,
            request.url.path,
        )
        return _build_error_response(
            error=exc.detail,
            error_code=exc.error_code,
            status_code=exc.status_code,
            detail=exc.extra,
            job_id=exc.job_id,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.warning(
            "[VALIDATION_ERROR] path=%s | errors=%s", request.url.path, exc.errors()
        )
        return _build_error_response(
            error="Payload de requête invalide",
            error_code="VALIDATION_ERROR",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=exc.errors(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception(
            "[INTERNAL_ERROR] Exception non gérée | path=%s | error=%s",
            request.url.path,
            exc,
        )
        return _build_error_response(
            error="Une erreur interne inattendue est survenue",
            error_code="INTERNAL_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
