"""
conftest.py — Fixtures partagées pour toute la suite de tests.

CRITIQUE : get_settings() utilise @lru_cache(maxsize=1).
Sans cache_clear() entre les tests, le premier appel à get_settings()
cacherait l'instance pour toute la session pytest, rendant les monkeypatch
sur les variables d'environnement inefficaces pour les tests ultérieurs.
"""
import pytest

from app.config import get_settings

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


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """
    Réinitialise le cache lru_cache de get_settings() avant chaque test.
    autouse=True : appliqué automatiquement à tous les tests sans déclaration.
    """
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
