"""HTTP-Views für Plant Care (Phase 2.1: Foto-Upload)."""
from __future__ import annotations

import base64
import binascii
import logging
import pathlib
import uuid

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import PHOTOS_DIRNAME, PHOTOS_URL_PATH, UPLOAD_URL_PATH

_LOGGER = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_MIME = {"image/jpeg", "image/jpg", "image/png", "image/webp"}

# Damit ai_task `attachments` per media-source resolved werden kann,
# müssen die Fotos unterhalb von hass.config.media_dirs['local'] liegen
# (Default: /config/media). Sonst → unknown_media_source.
LOCAL_MEDIA_KEY = "local"


def get_photos_dir(hass: HomeAssistant) -> pathlib.Path:
    """Foto-Ordner unterhalb des Local-Media-Source-Roots."""
    media_dirs = getattr(hass.config, "media_dirs", None) or {}
    base = media_dirs.get(LOCAL_MEDIA_KEY) or hass.config.path("media")
    return pathlib.Path(base) / PHOTOS_DIRNAME


async def save_uploaded_photo(
    hass: HomeAssistant, image_base64: str, mime: str = "image/jpeg"
) -> str:
    """Speichert ein Base64-Bild als Datei und gibt den URL-Pfad zurück.

    Gemeinsamer Code-Pfad für die HTTP-View und den add_plant_photo-Service.
    Wirft ``ValueError`` bei MIME-/Größen-/Decode-Fehlern.
    """
    b64 = image_base64.split(",", 1)[-1] if "," in image_base64 else image_base64
    if mime not in ALLOWED_MIME:
        raise ValueError(f"MIME-Typ nicht erlaubt: {mime}")
    try:
        data = base64.b64decode(b64, validate=True)
    except (ValueError, binascii.Error) as err:
        raise ValueError(f"Ungültige Base64-Daten: {err}") from err
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Datei zu groß")
    ext = "jpg" if mime in ("image/jpeg", "image/jpg") else mime.split("/")[1]
    fname = f"{uuid.uuid4().hex}.{ext}"
    photos_dir = get_photos_dir(hass)

    def _write() -> None:
        photos_dir.mkdir(parents=True, exist_ok=True)
        (photos_dir / fname).write_bytes(data)

    await hass.async_add_executor_job(_write)
    _LOGGER.info("Plant Care: Foto gespeichert als %s", fname)
    return f"{PHOTOS_URL_PATH}/{fname}"


class PlantPhotoUploadView(HomeAssistantView):
    """Nimmt Base64-kodierte Fotos entgegen und legt sie als Datei ab."""

    url = UPLOAD_URL_PATH
    name = "api:plant_care:upload"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def post(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except ValueError:
            return self.json_message("Ungültiges JSON", status_code=400)
        raw_b64 = body.get("image_base64", "")
        mime = body.get("mime", "image/jpeg")
        if not isinstance(raw_b64, str) or not raw_b64:
            return self.json_message("image_base64 fehlt", status_code=400)
        try:
            path = await save_uploaded_photo(self._hass, raw_b64, mime)
        except ValueError as err:
            status = 413 if "zu groß" in str(err) else 400
            return self.json_message(str(err), status_code=status)
        fname = path.rsplit("/", 1)[-1]
        return self.json(
            {
                "path": path,
                "media_content_id": (
                    f"media-source://media_source/{LOCAL_MEDIA_KEY}/"
                    f"{PHOTOS_DIRNAME}/{fname}"
                ),
                "media_content_type": mime,
            }
        )
