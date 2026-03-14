"""
models.py — Modèles Pydantic v2 pour tout le pipeline VideoGen
Couvre : entrée n8n → Claude → ElevenLabs → Kling/Pexels/Library → Creatomate → sortie

Structure calquée sur le PRD §4 (modules techniques détaillés).
"""
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


# ══════════════════════════════════════════════════════════════════════════════
# ENUMS
# ══════════════════════════════════════════════════════════════════════════════

class VideoFormat(str, Enum):
    """Format de sortie vidéo. Colonnes Sheets : 'vertical' / 'horizontal'."""
    VERTICAL = "vertical"      # 9:16  — Instagram/Facebook Reels
    HORIZONTAL = "horizontal"  # 16:9  — YouTube


class GenerationStrategy(str, Enum):
    """Stratégie de génération des B-rolls. PRD §3."""
    A = "A"  # Kling pur — 100% IA générative, unique par pub
    B = "B"  # Hybride — Library + Pexels + Kling en dernier recours


class ClipSource(str, Enum):
    """Source d'un clip vidéo dans le pipeline."""
    KLING = "kling"
    PEXELS = "pexels"
    LIBRARY = "library"  # Bibliothèque locale Stratégie B


class JobStatus(str, Enum):
    """États possibles d'un job de génération vidéo."""
    PENDING = "pending"
    QUEUED = "queued"                       # En attente de slot dans la queue
    RUNNING_CLAUDE = "running_claude"
    RUNNING_ELEVENLABS = "running_elevenlabs"
    RUNNING_CLIPS = "running_clips"         # Kling / Library / Pexels
    RUNNING_CREATOMATE = "running_creatomate"
    UPLOADING = "uploading"                 # Upload Drive (géré par n8n)
    COMPLETED = "completed"
    FAILED = "failed"


class SceneType(str, Enum):
    """Types de scènes définis par Claude pour le B-roll."""
    EMOTION = "emotion"
    PRODUCT = "product"
    TESTIMONIAL = "testimonial"
    CTA = "cta"
    AMBIENT = "ambient"
    TUTORIAL = "tutorial"


# ══════════════════════════════════════════════════════════════════════════════
# ENTRÉE — Données depuis Google Sheets via n8n
# ══════════════════════════════════════════════════════════════════════════════

class SheetsRow(BaseModel):
    """Représente une ligne Google Sheets validée (statut = OK)."""
    row_id: str = Field(..., description="Identifiant unique de la ligne (ex: 'row_12')")
    script: str = Field(..., min_length=50, description="Script publicitaire complet")
    format: VideoFormat = VideoFormat.VERTICAL
    strategy: GenerationStrategy = GenerationStrategy.A
    duration: int = Field(60, ge=15, le=90, description="Durée cible en secondes (15–90s, libre)")
    voice_id: str = Field(..., description="ID du clone vocal ElevenLabs pour cette campagne")
    music_url: str | None = Field(None, description="URL de la musique de fond")
    cta: str = Field("", max_length=200, description="Texte du call-to-action final")
    logo_url: str | None = Field(None, description="Override URL logo (sinon config.py)")
    persona: str | None = Field(None, description="Description du protagoniste visuel (genre, âge, apparence)")
    ambiance: str | None = Field(None, description="Style visuel souhaité (tonalité, lumière, palette)")

    # I3 fix étendu : strip \r\n et espaces sur tous les champs string venant de Sheets
    # Google Sheets + n8n peuvent inclure des \r\n en fin de cellule (Windows CRLF)
    @field_validator("voice_id", "script", "cta", "music_url", "logo_url", "persona", "ambiance", mode="before")
    @classmethod
    def strip_sheets_strings(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v

    @field_validator("duration")
    @classmethod
    def validate_duration(cls, v: int) -> int:
        # Toute valeur entre 15s et 90s est acceptée — le client choisit librement
        return v

    @property
    def aspect_ratio(self) -> str:
        return "9:16" if self.format == VideoFormat.VERTICAL else "16:9"


class VideoGenerationRequest(BaseModel):
    """Payload complet envoyé par n8n à POST /generate."""
    job_id: UUID = Field(default_factory=uuid4)
    sheets_row: SheetsRow
    # URL webhook n8n pour callback quand le job est terminé
    webhook_url: str | None = Field(None, description="Webhook n8n pour notification finale")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ══════════════════════════════════════════════════════════════════════════════
# MODULE CLAUDE — Découpage script + prompts B-roll (PRD §4.1)
# ══════════════════════════════════════════════════════════════════════════════

class ScriptSection(BaseModel):
    """
    Une section du script avec son B-roll prompt.
    Sortie JSON de Claude (PRD §4.1 exemple JSON).
    """
    id: int = Field(..., ge=1)
    text: str = Field(..., min_length=1, description="Texte narré dans cette section")
    start: int = Field(..., ge=0, description="Timecode de début en secondes")
    end: int = Field(..., gt=0, description="Timecode de fin en secondes")
    duration: int = Field(..., gt=0, description="Durée de la section en secondes")
    broll_prompt: str = Field(
        ..., min_length=10,
        description="Prompt Kling-compatible avec style, action, cadrage et ratio (ex: 9:16)",
    )
    keywords: list[str] = Field(default_factory=list, description="Mots-clés pour Library/Pexels")
    scene_type: SceneType = SceneType.AMBIENT

    @model_validator(mode="after")
    def validate_timecodes(self) -> "ScriptSection":
        if self.end <= self.start:
            raise ValueError(f"Section {self.id}: end ({self.end}) doit être > start ({self.start})")
        if self.duration != self.end - self.start:
            raise ValueError(
                f"Section {self.id}: duration ({self.duration}) ≠ end-start ({self.end - self.start})"
            )
        return self


class ScriptAnalysis(BaseModel):
    """
    Résultat complet de l'analyse Claude du script.
    Validation stricte : somme des durées == total_duration (PRD §4.1).
    """
    total_duration: int = Field(..., gt=0, description="Durée totale en secondes")
    source: Literal["claude", "parser"] = Field(
        "claude", description="Origine de l'analyse : Claude API ou parser pré-découpé"
    )
    sections: list[ScriptSection] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_total_duration(self) -> "ScriptAnalysis":
        computed = sum(s.duration for s in self.sections)
        if computed != self.total_duration:
            raise ValueError(
                f"Somme des durées ({computed}s) ≠ total_duration ({self.total_duration}s). "
                "Claude doit être relancé avec ce contexte d'erreur."
            )
        return self

    @property
    def section_count(self) -> int:
        return len(self.sections)


# ══════════════════════════════════════════════════════════════════════════════
# MODULE ELEVENLABS — Voix off + timestamps (PRD §4.2)
# ══════════════════════════════════════════════════════════════════════════════

class WordTimestamp(BaseModel):
    """Timestamp mot par mot fourni par ElevenLabs. Utilisé pour les sous-titres Creatomate."""
    word: str
    start_ms: int = Field(..., ge=0)
    end_ms: int = Field(..., gt=0)

    @model_validator(mode="after")
    def validate_timing(self) -> "WordTimestamp":
        if self.end_ms <= self.start_ms:
            raise ValueError(f"Mot '{self.word}': end_ms doit être > start_ms")
        return self


class ElevenLabsResult(BaseModel):
    """Résultat ElevenLabs : fichier audio + timestamps. PRD §4.2."""
    # Chemin local sur VPS ou URL signée
    audio_path: str = Field(..., description="Chemin/URL vers le fichier MP3 généré")
    audio_duration_ms: int = Field(..., gt=0, description="Durée audio réelle en ms")
    timestamps: list[WordTimestamp] = Field(
        default_factory=list, description="Timestamps mot par mot pour sous-titres"
    )
    voice_id: str
    character_count: int = Field(..., gt=0)

    @property
    def audio_duration_seconds(self) -> float:
        return self.audio_duration_ms / 1000.0


# ══════════════════════════════════════════════════════════════════════════════
# MODULE KLING — Génération clips asynchrone (PRD §4.3)
# ══════════════════════════════════════════════════════════════════════════════

class KlingJobStatus(str, Enum):
    """États internes d'un job Kling (distinct de JobStatus global)."""
    SUBMITTED = "submitted"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class KlingJob(BaseModel):
    """Suivi d'un job de génération Kling en cours."""
    kling_job_id: str
    section_id: int
    prompt: str
    status: KlingJobStatus = KlingJobStatus.SUBMITTED
    attempt: int = Field(1, ge=1, le=3)  # Retry x3 max (PRD §4.3)
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    error_message: str | None = None


# ══════════════════════════════════════════════════════════════════════════════
# CLIPS VIDÉO — Résultat commun Kling / Pexels / Library
# ══════════════════════════════════════════════════════════════════════════════

class VideoClip(BaseModel):
    """Un clip vidéo prêt à être passé à Creatomate."""
    section_id: int = Field(..., ge=1)
    source: ClipSource
    # Chemin local ou URL (Pexels/Kling retournent des URLs)
    url: str = Field(..., description="Chemin/URL du fichier MP4")
    duration_seconds: float = Field(..., gt=0)
    width: int | None = None
    height: int | None = None
    # Traçabilité
    prompt_used: str | None = Field(None, description="Prompt Kling utilisé")
    keywords_used: list[str] | None = Field(None, description="Keywords Pexels/Library")
    library_clip_id: str | None = Field(None, description="ID clip si source=LIBRARY")

    @property
    def is_fallback(self) -> bool:
        """True si le clip est un fallback (Pexels/Library) non généré par Kling."""
        return self.source in (ClipSource.PEXELS, ClipSource.LIBRARY)


# ══════════════════════════════════════════════════════════════════════════════
# MODULE LIBRARY — Index bibliothèque clips (Stratégie B)
# ══════════════════════════════════════════════════════════════════════════════

class LibraryClip(BaseModel):
    """Entrée dans l'index JSON de la bibliothèque de clips. PRD §3 Stratégie B."""
    clip_id: str = Field(default_factory=lambda: str(uuid4()))
    filename: str
    theme: str
    keywords: list[str]
    duration_seconds: float
    format: VideoFormat
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_used_at: datetime | None = None
    use_count: int = 0
    # Score de pertinence Claude pour la dernière utilisation
    last_relevance_score: float | None = None


class LibrarySearchResult(BaseModel):
    """Résultat de la recherche dans la bibliothèque."""
    clip: LibraryClip
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    matched_keywords: list[str]


# ══════════════════════════════════════════════════════════════════════════════
# MODULE CREATOMATE — Assemblage final (PRD §4.4)
# ══════════════════════════════════════════════════════════════════════════════

class CreatomateRenderRequest(BaseModel):
    """Payload d'assemblage envoyé à Creatomate. PRD §4.4."""
    template_id: str
    audio_url: str                        # MP3 voix off ElevenLabs
    clips: list[VideoClip]               # Clips ordonnés par section_id
    timestamps: list[WordTimestamp]       # Sous-titres mot par mot
    logo_url: str | None = None
    cta_text: str = ""
    music_url: str | None = None
    format: VideoFormat = VideoFormat.VERTICAL
    # Durée réelle de la voix off (audio_duration_seconds) — cap la composition
    # Évite que les clips Pexels (naturellement 15-60s) allongent la vidéo
    target_duration_seconds: float | None = Field(
        None, description="Durée cible composition = durée audio ElevenLabs"
    )

    @model_validator(mode="after")
    def validate_clips_ordered(self) -> "CreatomateRenderRequest":
        ids = [c.section_id for c in self.clips]
        if ids != sorted(ids):
            raise ValueError("Les clips doivent être ordonnés par section_id croissant")
        return self


class CreatomateRenderResult(BaseModel):
    """Résultat du rendu Creatomate."""
    render_id: str
    video_url: str = Field(..., description="URL publique de la vidéo MP4 finale")
    duration_seconds: float
    file_size_bytes: int | None = None
    format: VideoFormat
    rendered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ══════════════════════════════════════════════════════════════════════════════
# JOB — État global d'une génération (in-memory Day 1, Redis Day 2)
# ══════════════════════════════════════════════════════════════════════════════

class JobProgress(BaseModel):
    """Progression détaillée du job (affiché dans Sheets colonne 'Statut détail')."""
    status: JobStatus
    step: str                            # Libellé lisible ex: "Génération des clips vidéo"
    percentage: int = Field(0, ge=0, le=100)
    detail: str = ""
    # Pour le suivi Kling : nb clips prêts / total
    clips_done: int | None = None
    clips_total: int | None = None


class VideoJob(BaseModel):
    """État complet d'un job de génération vidéo (stocké en mémoire ou Redis)."""
    job_id: UUID
    row_id: str
    status: JobStatus = JobStatus.PENDING
    progress: JobProgress = Field(
        default_factory=lambda: JobProgress(
            status=JobStatus.PENDING, step="En attente", percentage=0
        )
    )
    request: VideoGenerationRequest

    # Résultats intermédiaires (pour debug et retry)
    script_analysis: ScriptAnalysis | None = None
    elevenlabs_result: ElevenLabsResult | None = None
    clips: list[VideoClip] | None = None

    # Résultat final
    render_result: CreatomateRenderResult | None = None
    drive_url: str | None = None         # URL finale Google Drive

    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ══════════════════════════════════════════════════════════════════════════════
# API RESPONSES — Réponses publiques des endpoints FastAPI
# ══════════════════════════════════════════════════════════════════════════════

class JobCreatedResponse(BaseModel):
    """Réponse immédiate de POST /generate (job démarré en background)."""
    job_id: UUID
    status: JobStatus
    message: str
    status_url: str = Field(..., description="URL pour suivre le statut : GET /status/{job_id}")


class JobStatusResponse(BaseModel):
    """Réponse de GET /status/{job_id}."""
    job_id: UUID
    row_id: str
    status: JobStatus
    progress: JobProgress
    drive_url: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class HealthResponse(BaseModel):
    """Réponse de GET /health."""
    status: str = "ok"
    version: str
    environment: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ErrorResponse(BaseModel):
    """Format standard d'erreur pour tous les endpoints."""
    error: str
    error_code: str
    detail: Any = None
    job_id: UUID | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ══════════════════════════════════════════════════════════════════════════════
# NOTIFICATIONS — Payloads webhook vers n8n (PRD §5.2)
# ══════════════════════════════════════════════════════════════════════════════

class NotificationType(str, Enum):
    SUCCESS = "success"
    PARTIAL_ERROR = "partial_error"
    BLOCKING_ERROR = "blocking_error"
    CREDIT_ALERT = "credit_alert"


class NotificationPayload(BaseModel):
    """Payload envoyé au webhook n8n pour notifications (PRD §5.2)."""
    type: NotificationType
    job_id: UUID
    row_id: str
    # Numéro de ligne Sheets (entier) — utilisé par le workflow FINALISATION
    # pour la mise à jour Google Sheets via matchingColumns: ["row_number"]
    row_number: int | None = None
    message: str
    drive_url: str | None = None         # Pour type=SUCCESS
    error_detail: str | None = None      # Pour partial/blocking error
    affected_step: str | None = None     # Ex: "Kling clip section 4"
    corrective_action: str | None = None # Suggestion d'action
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
