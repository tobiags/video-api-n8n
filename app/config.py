"""
config.py — Configuration centralisée VideoGen API
Toutes les clés API + paramètres lus depuis .env via pydantic-settings.
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────────────
    APP_NAME: str = "VideoGen API"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False

    # ── Server ───────────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    # NOTE: garder WORKERS=1 jusqu'au Jour 2 (Redis) — l'in-memory job store
    # n'est pas partageable entre plusieurs workers Gunicorn.
    WORKERS: int = 1
    # Limite de pipelines en parallèle (Semaphore asyncio) — les jobs supplémentaires
    # sont mis en file d'attente (statut QUEUED) jusqu'à la libération d'un slot.
    # Valeur recommandée : 2 (Kling + Creatomate sont lourds en parallèle)
    MAX_CONCURRENT_JOBS: int = Field(2, ge=1, le=5)

    # ── Sécurité ─────────────────────────────────────────────────────────────
    # Secret partagé entre n8n et FastAPI (header: Authorization: Bearer <token>)
    API_SECRET_KEY: SecretStr = Field(..., description="Secret partagé n8n ↔ FastAPI")

    # ── Claude / Anthropic ───────────────────────────────────────────────────
    ANTHROPIC_API_KEY: SecretStr = Field(...)
    CLAUDE_MODEL: str = "claude-opus-4-6"
    CLAUDE_MAX_TOKENS: int = 4096
    # Nombre de tentatives si Claude retourne un JSON invalide (PRD §4.1)
    CLAUDE_MAX_RETRIES: int = 3

    # ── ElevenLabs ───────────────────────────────────────────────────────────
    ELEVENLABS_API_KEY: SecretStr = Field(...)
    ELEVENLABS_BASE_URL: str = "https://api.elevenlabs.io/v1"
    ELEVENLABS_MODEL_ID: str = "eleven_multilingual_v2"
    # ID du clone vocal par défaut (peut être surchargé ligne par ligne dans Sheets)
    ELEVENLABS_DEFAULT_VOICE_ID: str = Field(..., description="ID clone vocal ElevenLabs")
    # Retry x2 avec backoff exponentiel (PRD §5.1)
    ELEVENLABS_MAX_RETRIES: int = 2
    ELEVENLABS_BACKOFF_BASE: float = 5.0  # secondes (5s, 10s)
    # Vitesse de lecture (0.7 = lent/posé, 1.0 = normal, 1.2 = rapide)
    # Valeur recommandée : 0.85 pour une voix pub "posée" et professionnelle
    ELEVENLABS_VOICE_SPEED: float = Field(0.85, ge=0.7, le=1.2)

    # ── Kling AI ─────────────────────────────────────────────────────────────
    KLING_ACCESS_KEY: SecretStr = Field(...)
    KLING_SECRET_KEY: SecretStr = Field(...)
    KLING_BASE_URL: str = "https://api.klingai.com"
    KLING_MODEL: str = "kling-v1-6"
    KLING_DURATION: int = 5          # durée cible par clip en secondes
    KLING_NATIVE_AUDIO: bool = False # désactivé : on n'a pas besoin de l'audio IA Kling (économie crédits)
    # Limite API officielle : max 5 en parallèle, mais le rate limit burst est ~2/s
    # Garder à 2 pour éviter les 429 en rafale sur 14 clips simultanés
    KLING_MAX_PARALLEL_JOBS: int = 2
    # Polling toutes les 30 sec, timeout 10 min par clip (PRD §4.3)
    KLING_POLLING_INTERVAL: float = 30.0
    KLING_CLIP_TIMEOUT: int = 600    # 10 minutes max par clip
    KLING_MAX_RETRIES: int = 3       # retry auto x3 puis fallback Pexels (PRD §5.1)

    # ── Pexels (fallback gratuit Stratégie B) ────────────────────────────────
    PEXELS_API_KEY: SecretStr = Field(...)
    PEXELS_BASE_URL: str = "https://api.pexels.com/v1"

    # ── Creatomate ───────────────────────────────────────────────────────────
    CREATOMATE_API_KEY: SecretStr = Field(...)
    CREATOMATE_BASE_URL: str = "https://api.creatomate.com/v2"
    # Plus utilisés — on passe à l'approche "source" dynamique (pas de templates statiques)
    CREATOMATE_TEMPLATE_VERTICAL: str = Field("", description="Obsolète — approche source dynamique")
    CREATOMATE_TEMPLATE_HORIZONTAL: str = Field("", description="Obsolète — approche source dynamique")
    CREATOMATE_SHOW_CTA: bool = False    # True pour réactiver le texte CTA overlay
    CREATOMATE_POLLING_INTERVAL: float = 15.0
    CREATOMATE_RENDER_TIMEOUT: int = 900  # 15 min max
    CREATOMATE_MAX_RETRIES: int = 2

    # ── Google ───────────────────────────────────────────────────────────────
    GOOGLE_SERVICE_ACCOUNT_PATH: str = Field(
        "/opt/videogen/service_account.json",
        description="Chemin vers le JSON de service account Google",
    )
    GOOGLE_DRIVE_FOLDER_ID: str = Field(..., description="ID dossier Google Drive de destination")
    GOOGLE_SHEETS_ID: str = Field(..., description="ID du Google Sheets de campagnes")
    GOOGLE_SHEETS_TAB: str = "Campagnes"

    # Colonnes Google Sheets (positions 0-indexées, configurable si la structure change)
    SHEETS_COL_SCRIPT: int = 0
    SHEETS_COL_STATUT: int = 1
    SHEETS_COL_FORMAT: int = 2
    SHEETS_COL_STRATEGIE: int = 3
    SHEETS_COL_DUREE: int = 4
    SHEETS_COL_VOIX: int = 5
    SHEETS_COL_MUSIQUE: int = 6
    SHEETS_COL_CTA: int = 7
    SHEETS_COL_LIEN_OUTPUT: int = 8
    SHEETS_COL_STATUT_DETAIL: int = 9

    # ── Stratégie B — Bibliothèque clips ────────────────────────────────────
    LIBRARY_PATH: str = "/opt/videogen/library/clips"
    LIBRARY_INDEX_FILE: str = "/opt/videogen/library/index.json"
    # Score minimal de pertinence Claude pour réutiliser un clip existant (PRD §3)
    LIBRARY_SCORE_THRESHOLD: float = 0.7
    # Archiver les clips non utilisés depuis N jours (PRD §3)
    LIBRARY_CLEANUP_DAYS: int = 90

    # ── HTTP Client ──────────────────────────────────────────────────────────
    HTTP_TIMEOUT_DEFAULT: float = 30.0
    HTTP_TIMEOUT_VIDEO_GEN: float = 1200.0  # Pour Kling/Creatomate polling (CREATOMATE_RENDER_TIMEOUT=900 + overhead)
    HTTP_MAX_CONNECTIONS: int = 20
    HTTP_MAX_KEEPALIVE: int = 10

    # ── Monitoring / Sentry ──────────────────────────────────────────────────────
    # DSN optionnel — si absent, Sentry est désactivé (dev local, tests)
    SENTRY_DSN: str | None = None

    # ── Notifications ────────────────────────────────────────────────────────
    # URL webhook n8n pour callbacks (succès, erreur, alerte crédits)
    N8N_WEBHOOK_NOTIFICATION_URL: str | None = None
    # Seuil d'alerte crédits API : notif à 20% restant (PRD §5.1)
    API_CREDIT_ALERT_THRESHOLD: float = 0.20

    # ── Sécurité réseau ──────────────────────────────────────────────────────
    # Hosts autorisés pour TrustedHostMiddleware en production.
    # Inclure le domaine nginx (ex: "videogen.example.com") + localhost.
    # Valeur par défaut : localhost only (communic. n8n sur même VPS).
    TRUSTED_HOSTS: list[str] = Field(
        default=["localhost", "127.0.0.1"],
        description="Hosts autorisés en production (inclure domaine VPS si derrière nginx)",
    )

    # ── Logo ─────────────────────────────────────────────────────────────────
    LOGO_URL: str | None = None  # URL publique du logo intégré par Creatomate

    # ── URL publique de l'API ─────────────────────────────────────────────────
    # Nécessaire pour construire les URLs audio accessibles par Creatomate.
    # Ex: "http://ys4o0cosg48gk0o4g4o8o4kw.95.217.220.12.sslip.io"
    API_BASE_URL: str = ""

    # ── Validators ───────────────────────────────────────────────────────────
    @field_validator("ENVIRONMENT", mode="before")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        return v.lower()

    @field_validator("KLING_MAX_PARALLEL_JOBS")
    @classmethod
    def validate_kling_parallel(cls, v: int) -> int:
        if v > 5:
            raise ValueError("KLING_MAX_PARALLEL_JOBS ne peut pas dépasser 5 (limite API officielle)")
        return v

    # ── Propriétés (expose les SecretStr de façon contrôlée) ─────────────────
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def anthropic_api_key(self) -> str:
        return self.ANTHROPIC_API_KEY.get_secret_value()

    @property
    def elevenlabs_api_key(self) -> str:
        return self.ELEVENLABS_API_KEY.get_secret_value()

    @property
    def kling_access_key(self) -> str:
        return self.KLING_ACCESS_KEY.get_secret_value()

    @property
    def kling_secret_key(self) -> str:
        return self.KLING_SECRET_KEY.get_secret_value()

    @property
    def pexels_api_key(self) -> str:
        return self.PEXELS_API_KEY.get_secret_value()

    @property
    def creatomate_api_key(self) -> str:
        return self.CREATOMATE_API_KEY.get_secret_value()

    @property
    def api_secret_key(self) -> str:
        return self.API_SECRET_KEY.get_secret_value()

    @property
    def elevenlabs_default_voice_id(self) -> str:
        return self.ELEVENLABS_DEFAULT_VOICE_ID


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton Settings — chargé une seule fois au démarrage."""
    return Settings()
