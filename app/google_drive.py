"""
Upload de vidéos vers Google Drive via Service Account.

Utilise google-api-python-client (déjà dans requirements.txt).
Le service account doit avoir accès au dossier GOOGLE_DRIVE_FOLDER_ID.
"""
import asyncio
import io
import logging

import httpx
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from app.config import Settings

logger = logging.getLogger("app.google_drive")

_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def _upload_sync(video_bytes: bytes, filename: str, settings: Settings) -> str:
    """Synchrone — upload vers Drive, retourne le webViewLink."""
    creds = service_account.Credentials.from_service_account_file(
        settings.GOOGLE_SERVICE_ACCOUNT_PATH, scopes=_SCOPES
    )
    service = build("drive", "v3", credentials=creds, cache_discovery=False)

    file_metadata = {
        "name": filename,
        "parents": [settings.GOOGLE_DRIVE_FOLDER_ID],
    }
    media = MediaIoBaseUpload(
        io.BytesIO(video_bytes),
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024,  # 10 MB chunks
    )
    file = (
        service.files()
        .create(body=file_metadata, media_body=media, fields="id,webViewLink")
        .execute()
    )

    # Rendre le fichier accessible à tous via le lien
    service.permissions().create(
        fileId=file["id"],
        body={"type": "anyone", "role": "reader"},
    ).execute()

    url = file.get("webViewLink", "")
    logger.info("Drive upload OK | file_id=%s | url=%s", file["id"], url)
    return url


async def upload_video_to_drive(
    video_url: str,
    filename: str,
    http_client: httpx.AsyncClient,
    settings: Settings,
) -> str:
    """
    Télécharge la vidéo depuis video_url et l'uploade sur Google Drive.
    Retourne le webViewLink (URL Drive partageable).
    """
    logger.info("Drive upload — téléchargement depuis Creatomate: %s", video_url)
    resp = await http_client.get(video_url, timeout=300.0, follow_redirects=True)
    resp.raise_for_status()
    video_bytes = resp.content
    size_mb = len(video_bytes) / 1_048_576
    logger.info("Vidéo téléchargée (%.1f MB) — upload vers Drive...", size_mb)

    loop = asyncio.get_event_loop()
    drive_url = await loop.run_in_executor(
        None, _upload_sync, video_bytes, filename, settings
    )
    return drive_url
