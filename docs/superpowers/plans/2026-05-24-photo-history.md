# Foto-Verlauf / Growth Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pflanzen-Detail-View bekommt einen Foto-Verlauf-Strip mit Lightbox und Side-by-Side-Vergleich.

**Architecture:** Plant-Dict bekommt `photos: list[{path, taken_at, note}]` zusätzlich zum bestehenden `photo`-Top-Level-Feld (Backwards-Compat). Migration läuft idempotent in `async_load`. Zwei neue Services (`add_plant_photo`, `remove_plant_photo`) für Frontend-Pipeline.

**Tech Stack:** Home Assistant Custom Integration, pytest, Vanilla-JS-Web-Component.

**Spec:** [docs/superpowers/specs/2026-05-24-photo-history-design.md](../specs/2026-05-24-photo-history-design.md)

---

### Task 1: Pure Helper in `_utils.py` (TDD)

**Files:**
- Modify: `custom_components/plant_care/_utils.py`
- Modify: `tests/test_utils.py`

- [ ] **Step 1.1: Tests für `sort_photos` schreiben**

In `tests/test_utils.py`, am Ende vor letztem Test:

```python
# --------------------------- sort_photos ---------------------------

def test_sort_photos_empty():
    assert sort_photos([]) == []


def test_sort_photos_descending_by_taken_at():
    photos = [
        {"path": "/a.jpg", "taken_at": "2026-01-01T00:00:00+00:00"},
        {"path": "/b.jpg", "taken_at": "2026-05-01T00:00:00+00:00"},
        {"path": "/c.jpg", "taken_at": "2026-03-01T00:00:00+00:00"},
    ]
    result = sort_photos(photos)
    assert [p["path"] for p in result] == ["/b.jpg", "/c.jpg", "/a.jpg"]


def test_sort_photos_missing_taken_at_goes_last():
    photos = [
        {"path": "/old.jpg", "taken_at": "2026-01-01T00:00:00+00:00"},
        {"path": "/notime.jpg"},
        {"path": "/new.jpg", "taken_at": "2026-05-01T00:00:00+00:00"},
    ]
    result = sort_photos(photos)
    assert [p["path"] for p in result] == ["/new.jpg", "/old.jpg", "/notime.jpg"]
```

- [ ] **Step 1.2: Tests für `migrate_legacy_photo` schreiben**

```python
# --------------------------- migrate_legacy_photo ---------------------------

def test_migrate_legacy_photo_no_photo_creates_empty_list():
    plant = {"name": "X"}
    migrated = migrate_legacy_photo(plant)
    assert migrated is True
    assert plant["photos"] == []


def test_migrate_legacy_photo_empty_photo_creates_empty_list():
    plant = {"name": "X", "photo": ""}
    migrated = migrate_legacy_photo(plant)
    assert migrated is True
    assert plant["photos"] == []


def test_migrate_legacy_photo_with_path_creates_entry():
    plant = {
        "name": "X",
        "photo": "/api/plant_care/photos/abc.jpg",
        "created": "2026-01-01T00:00:00+00:00",
    }
    migrated = migrate_legacy_photo(plant)
    assert migrated is True
    assert plant["photos"] == [
        {
            "path": "/api/plant_care/photos/abc.jpg",
            "taken_at": "2026-01-01T00:00:00+00:00",
            "note": "",
        }
    ]


def test_migrate_legacy_photo_idempotent():
    plant = {
        "name": "X",
        "photo": "/api/plant_care/photos/abc.jpg",
        "photos": [{"path": "/already.jpg", "taken_at": "2026-01-01T00:00:00+00:00", "note": ""}],
    }
    migrated = migrate_legacy_photo(plant)
    assert migrated is False
    assert plant["photos"] == [{"path": "/already.jpg", "taken_at": "2026-01-01T00:00:00+00:00", "note": ""}]
```

- [ ] **Step 1.3: Tests für `cap_photos` schreiben**

```python
# --------------------------- cap_photos ---------------------------

def test_cap_photos_under_limit():
    photos = [{"path": f"/{i}.jpg", "taken_at": f"2026-0{i+1}-01T00:00:00+00:00"} for i in range(3)]
    kept, removed = cap_photos(photos, max_count=5)
    assert kept == photos
    assert removed == []


def test_cap_photos_at_limit():
    photos = [{"path": f"/{i}.jpg", "taken_at": f"2026-0{i+1}-01T00:00:00+00:00"} for i in range(5)]
    kept, removed = cap_photos(photos, max_count=5)
    assert kept == photos
    assert removed == []


def test_cap_photos_over_limit_keeps_newest():
    # Input ist DESC sortiert (Index 0 = neuestes).
    photos = [
        {"path": "/new.jpg",  "taken_at": "2026-05-01T00:00:00+00:00"},
        {"path": "/mid.jpg",  "taken_at": "2026-03-01T00:00:00+00:00"},
        {"path": "/old1.jpg", "taken_at": "2026-01-01T00:00:00+00:00"},
        {"path": "/old2.jpg", "taken_at": "2025-12-01T00:00:00+00:00"},
    ]
    kept, removed = cap_photos(photos, max_count=2)
    assert [p["path"] for p in kept] == ["/new.jpg", "/mid.jpg"]
    assert [p["path"] for p in removed] == ["/old1.jpg", "/old2.jpg"]
```

Imports ergänzen:

```python
from _utils import (  # type: ignore[import-not-found]
    cap_photos,
    clean_data,
    compute_snooze_last_notified,
    is_in_quiet_hours,
    is_rate_limited,
    migrate_legacy_photo,
    needs_time_based,
    parse_action_id,
    parse_iso,
    parse_time_string,
    sort_photos,
    try_float,
    utcnow_iso,
)
```

- [ ] **Step 1.4: Tests laufen lassen → Fail**

Run: `/tmp/pc-test/bin/python -m pytest tests/ -q 2>&1 | tail -5`
Expected: ImportError für die drei neuen Funktionen.

- [ ] **Step 1.5: Helper implementieren**

In `custom_components/plant_care/_utils.py`, am Ende:

```python
def sort_photos(photos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sortiert Fotos descending nach ``taken_at`` (neuestes zuerst).

    Fotos ohne ``taken_at`` landen ans Ende.
    """
    def _key(photo: dict[str, Any]) -> tuple[int, str]:
        ts = photo.get("taken_at")
        if not ts:
            # 0 = "fehlt" → wandert nach hinten beim reverse=True
            return (0, "")
        return (1, ts)

    return sorted(photos, key=_key, reverse=True)


def migrate_legacy_photo(plant: dict[str, Any]) -> bool:
    """Bringt eine Plant-Storage-Entry auf das neue Photo-Array-Schema.

    Returns:
        True wenn migriert wurde, False wenn bereits aktuell.
    """
    if "photos" in plant and isinstance(plant.get("photos"), list):
        return False
    legacy = plant.get("photo") or ""
    if legacy and isinstance(legacy, str):
        plant["photos"] = [
            {
                "path": legacy,
                "taken_at": plant.get("created") or utcnow_iso(),
                "note": "",
            }
        ]
    else:
        plant["photos"] = []
    return True


def cap_photos(
    photos: list[dict[str, Any]], max_count: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Kürzt die Foto-Liste auf ``max_count``.

    Annahme: Liste ist bereits descending sortiert (neuestes zuerst).

    Returns:
        (kept, removed). ``removed`` enthält die abgeschnittenen Einträge
        (älteste über dem Cap), damit der Caller deren Files vom Disk
        löschen kann.
    """
    if max_count <= 0 or len(photos) <= max_count:
        return list(photos), []
    return list(photos[:max_count]), list(photos[max_count:])
```

- [ ] **Step 1.6: Tests grün?**

Run: `/tmp/pc-test/bin/python -m pytest tests/ -q 2>&1 | tail -5`
Expected: 50 passed (40 alte + 10 neue).

- [ ] **Step 1.7: Commit**

```bash
git add custom_components/plant_care/_utils.py tests/test_utils.py
git commit -m "Add sort_photos, migrate_legacy_photo, cap_photos Helper

Pure Funktionen für das Photo-History-Schema:
- sort_photos: DESC nach taken_at, fehlendes Datum nach hinten
- migrate_legacy_photo: alter photo-String → photos-Array, idempotent
- cap_photos: Soft-Limit pro Pflanze, returnt removed-Liste fürs
  Disk-Cleanup beim Caller
"
```

---

### Task 2: Coordinator: Migration + add_plant_photo + remove_plant_photo

**Files:**
- Modify: `custom_components/plant_care/const.py`
- Modify: `custom_components/plant_care/coordinator.py`

- [ ] **Step 2.1: Konstante**

In `const.py`, nach `HISTORY_MAX_ENTRIES`:

```python
# Cap pro Pflanze
MAX_PHOTOS_PER_PLANT: Final = 100
```

- [ ] **Step 2.2: Imports im Coordinator ergänzen**

In `coordinator.py`, oben:

```python
from ._utils import (
    cap_photos,
    clean_data,
    compute_snooze_last_notified,
    is_in_quiet_hours,
    is_rate_limited,
    migrate_legacy_photo,
    parse_time_string,
    sort_photos,
    utcnow_iso,
)
```

```python
from .const import (
    CONF_NOTIFY_SERVICE,
    CONF_NOTIFY_TITLE,
    CONF_QUIET_HOURS_END,
    CONF_QUIET_HOURS_START,
    CONF_RATE_LIMIT_HOURS,
    CONF_REMINDERS_ENABLED,
    DEFAULT_FERTILIZE_DAYS,
    DEFAULT_NOTIFY_TITLE,
    DEFAULT_WATER_DAYS,
    DOMAIN,
    HISTORY_MAX_ENTRIES,
    MAX_PHOTOS_PER_PLANT,
    PHOTOS_URL_PATH,
    SIGNAL_NEW_PLANT,
    SIGNAL_PLANTS_UPDATED,
    SIGNAL_REMOVE_PLANT,
    SNOOZE_DEFAULT_HOURS,
    STATUS_NEEDS_BOTH,
    STATUS_NEEDS_FERTILIZER,
    STATUS_NEEDS_WATER,
    STATUS_OK,
    STORAGE_KEY,
    STORAGE_VERSION,
)
```

- [ ] **Step 2.3: Migration in `async_load`**

In `async_load`, im `for pid, plant in plants.items():`-Block die Zeile nach `plant.setdefault("last_notified", None)` ergänzen:

```python
            migrate_legacy_photo(plant)
```

- [ ] **Step 2.4: `_sync_primary_photo`-Helper**

In `PlantCareCoordinator`, vor `async_water_plant`:

```python
    def _sync_primary_photo(self, plant: dict[str, Any]) -> None:
        """Hält ``photo`` synchron mit ``photos[0]`` (Primärfoto).

        Wird nach jeder Modifikation des photos-Arrays aufgerufen, damit
        Lovelace-Karten / Sensor-Attribute, die ``photo`` direkt lesen,
        weiter funktionieren.
        """
        photos = plant.get("photos") or []
        plant["photo"] = photos[0]["path"] if photos else ""
```

- [ ] **Step 2.5: `async_add_plant_photo`**

Nach `async_snooze_plant` einfügen:

```python
    async def async_add_plant_photo(
        self,
        plant_id: str,
        path: str,
        note: str = "",
        taken_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Fügt einen Foto-Eintrag zur Pflanze hinzu.

        ``path`` muss ein gültiger Pfad auf eine bereits gespeicherte Datei
        sein (z.B. von ``PlantPhotoUploadView`` oder Service mit
        ``image_base64``). Der Upload selbst läuft außerhalb des Coordinators.

        Returns:
            ``{"path": ..., "index": 0}`` – der eingefügte Eintrag landet
            durch die DESC-Sortierung immer auf Index 0, sofern ``taken_at``
            der aktuellste Zeitstempel ist.
        """
        if plant_id not in self._plants:
            raise ValueError(f"Pflanze {plant_id} nicht gefunden")
        if not path:
            raise ValueError("path ist erforderlich")

        entry = {
            "path": path,
            "taken_at": (
                taken_at or datetime.now(timezone.utc)
            ).astimezone(timezone.utc).isoformat(),
            "note": note or "",
        }

        plant = self._plants[plant_id]
        photos = list(plant.get("photos") or [])
        photos.append(entry)
        photos = sort_photos(photos)

        kept, removed = cap_photos(photos, MAX_PHOTOS_PER_PLANT)
        plant["photos"] = kept
        self._sync_primary_photo(plant)

        # Files der abgeschnittenen Einträge vom Disk räumen.
        if removed:
            await self._delete_photo_files([p["path"] for p in removed])

        await self._async_save_now()
        async_dispatcher_send(self.hass, SIGNAL_PLANTS_UPDATED, plant_id)
        _LOGGER.debug(
            "Plant Care: Foto zu Pflanze %s hinzugefügt (%s)", plant_id, path
        )

        return {"path": path, "index": kept.index(entry) if entry in kept else 0}

    async def async_remove_plant_photo(
        self, plant_id: str, path: str, keep_file: bool = False
    ) -> None:
        """Entfernt einen Foto-Eintrag aus dem Verlauf.

        ``keep_file=False`` löscht zusätzlich die Datei vom Disk.
        """
        if plant_id not in self._plants:
            raise ValueError(f"Pflanze {plant_id} nicht gefunden")
        plant = self._plants[plant_id]
        photos = list(plant.get("photos") or [])
        original_len = len(photos)
        photos = [p for p in photos if p.get("path") != path]
        if len(photos) == original_len:
            raise ValueError(f"Foto {path} nicht im Verlauf von {plant_id}")

        plant["photos"] = photos
        self._sync_primary_photo(plant)

        if not keep_file:
            await self._delete_photo_files([path])

        await self._async_save_now()
        async_dispatcher_send(self.hass, SIGNAL_PLANTS_UPDATED, plant_id)
        _LOGGER.debug(
            "Plant Care: Foto %s aus %s entfernt", path, plant_id
        )

    async def _delete_photo_files(self, paths: list[str]) -> None:
        """Löscht die zu ``paths`` gehörenden Dateien aus dem Foto-Verzeichnis.

        Best-Effort: `missing_ok=True` und einzelne Fehler werden geloggt
        aber nicht propagiert. ``paths`` sind URL-Pfade
        (`/api/plant_care/photos/abc.jpg`); wir mappen auf den Dateinamen.
        """
        photos_dir = get_photos_dir(self.hass)

        def _unlink_all() -> None:
            for path in paths:
                if not path or not path.startswith(PHOTOS_URL_PATH):
                    continue
                fname = path[len(PHOTOS_URL_PATH):].lstrip("/")
                if not fname or "/" in fname or "\\" in fname or ".." in fname:
                    continue  # Schutz gegen Path-Traversal
                try:
                    (photos_dir / fname).unlink(missing_ok=True)
                except OSError as err:
                    _LOGGER.warning(
                        "Plant Care: Datei %s konnte nicht gelöscht werden: %s",
                        fname,
                        err,
                    )

        await self.hass.async_add_executor_job(_unlink_all)
```

- [ ] **Step 2.6: `async_remove_plant` löscht jetzt auch Files**

Bestehendes:

```python
    async def async_remove_plant(self, plant_id: str) -> None:
        """Löscht eine Pflanze."""
        if plant_id not in self._plants:
            raise ValueError(f"Pflanze {plant_id} nicht gefunden")
        del self._plants[plant_id]
        await self._async_save_now()
        async_dispatcher_send(self.hass, SIGNAL_REMOVE_PLANT, plant_id)
        _LOGGER.debug("Plant Care: Pflanze %s entfernt", plant_id)
```

Ersetzen durch:

```python
    async def async_remove_plant(self, plant_id: str) -> None:
        """Löscht eine Pflanze inklusive aller zugehörigen Foto-Files."""
        if plant_id not in self._plants:
            raise ValueError(f"Pflanze {plant_id} nicht gefunden")
        photos = list(self._plants[plant_id].get("photos") or [])
        del self._plants[plant_id]
        if photos:
            await self._delete_photo_files([p["path"] for p in photos])
        await self._async_save_now()
        async_dispatcher_send(self.hass, SIGNAL_REMOVE_PLANT, plant_id)
        _LOGGER.debug(
            "Plant Care: Pflanze %s entfernt (+%d Foto-Files)",
            plant_id,
            len(photos),
        )
```

- [ ] **Step 2.7: Sanity-Check + Commit**

```bash
python3 -m py_compile custom_components/plant_care/*.py && /tmp/pc-test/bin/python -m pytest tests/ -q | tail -3
```

Expected: alle Tests grün.

```bash
git add custom_components/plant_care/const.py custom_components/plant_care/coordinator.py
git commit -m "Coordinator: photos-Array, add/remove_plant_photo

- Schema-Migration in async_load (photo → photos[])
- async_add_plant_photo sortiert + capped (MAX_PHOTOS_PER_PLANT=100)
- async_remove_plant_photo räumt auch die Datei vom Disk
- async_remove_plant löscht jetzt auch alle Foto-Files der Pflanze
- _sync_primary_photo hält photo synchron mit photos[0]
"
```

---

### Task 3: Services registrieren

**Files:**
- Modify: `custom_components/plant_care/const.py`
- Modify: `custom_components/plant_care/__init__.py`
- Modify: `custom_components/plant_care/services.yaml`
- Modify: `custom_components/plant_care/strings.json`
- Modify: `custom_components/plant_care/translations/en.json`
- Modify: `custom_components/plant_care/translations/de.json`

- [ ] **Step 3.1: Service-Namen in const**

In `const.py`, in der Service-Liste:

```python
SERVICE_ADD_PLANT_PHOTO: Final = "add_plant_photo"
SERVICE_REMOVE_PLANT_PHOTO: Final = "remove_plant_photo"
```

- [ ] **Step 3.2: Schemas + Handler in `__init__.py`**

In `__init__.py`, Imports ergänzen:

```python
from .const import (
    ...
    SERVICE_ADD_PLANT_PHOTO,
    SERVICE_REMOVE_PLANT_PHOTO,
    ...
)
```

Schemas nach `WATER_SCHEMA` ergänzen:

```python
ADD_PLANT_PHOTO_SCHEMA = vol.Schema(
    {
        vol.Required("plant_id"): cv.string,
        vol.Exclusive("path", "source"): cv.string,
        vol.Exclusive("image_base64", "source"): cv.string,
        vol.Optional("mime", default="image/jpeg"): cv.string,
        vol.Optional("note", default=""): cv.string,
        vol.Optional("taken_at"): cv.datetime,
    }
)

REMOVE_PLANT_PHOTO_SCHEMA = vol.Schema(
    {
        vol.Required("plant_id"): cv.string,
        vol.Required("path"): cv.string,
        vol.Optional("keep_file", default=False): cv.boolean,
    }
)
```

Handler-Funktionen im `_register_services`, nach `handle_send_reminders`:

```python
    async def handle_add_plant_photo(call: ServiceCall) -> ServiceResponse:
        data = dict(call.data)
        plant_id = data["plant_id"]
        path = data.get("path")
        image_base64 = data.get("image_base64")
        if not path and not image_base64:
            raise vol.Invalid("Entweder path oder image_base64 muss gesetzt sein")
        if path is None and image_base64:
            # Upload-Pipeline aufrufen
            from .http import save_uploaded_photo
            path = await save_uploaded_photo(
                hass, image_base64, data.get("mime", "image/jpeg")
            )
        result = await coord.async_add_plant_photo(
            plant_id=plant_id,
            path=path,
            note=data.get("note", ""),
            taken_at=data.get("taken_at"),
        )
        return result

    async def handle_remove_plant_photo(call: ServiceCall) -> None:
        await coord.async_remove_plant_photo(
            plant_id=call.data["plant_id"],
            path=call.data["path"],
            keep_file=bool(call.data.get("keep_file", False)),
        )
```

Registrierung am Ende:

```python
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_PLANT_PHOTO,
        handle_add_plant_photo,
        schema=ADD_PLANT_PHOTO_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_PLANT_PHOTO,
        handle_remove_plant_photo,
        schema=REMOVE_PLANT_PHOTO_SCHEMA,
    )
```

Cleanup-Liste in `async_unload_entry` ergänzen:

```python
    for service in (
        SERVICE_ADD_PLANT,
        SERVICE_UPDATE_PLANT,
        SERVICE_REMOVE_PLANT,
        SERVICE_WATER_PLANT,
        SERVICE_FERTILIZE_PLANT,
        SERVICE_SEND_REMINDERS,
        SERVICE_ADD_PLANT_PHOTO,
        SERVICE_REMOVE_PLANT_PHOTO,
    ):
```

- [ ] **Step 3.3: `save_uploaded_photo` Helper aus `http.py` extrahieren**

In `http.py`, vor `class PlantPhotoUploadView`:

```python
async def save_uploaded_photo(
    hass: HomeAssistant, image_base64: str, mime: str = "image/jpeg"
) -> str:
    """Speichert ein Base64-Bild als Datei und gibt den URL-Pfad zurück.

    Gemeinsamer Code-Pfad für die HTTP-View und den
    ``add_plant_photo``-Service.
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
```

Und die `post`-Methode der View nutzt diesen Helper:

```python
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

        return self.json(
            {
                "path": path,
                "media_content_id": (
                    f"media-source://media_source/{LOCAL_MEDIA_KEY}/"
                    f"{PHOTOS_DIRNAME}/{path.rsplit('/', 1)[-1]}"
                ),
                "media_content_type": mime,
            }
        )
```

- [ ] **Step 3.4: services.yaml ergänzen**

In `services.yaml`, nach `send_reminders`:

```yaml
add_plant_photo:
  name: Foto hinzufügen
  description: >
    Fügt ein Foto zum Verlauf einer Pflanze hinzu. Entweder ein
    `path` (auf eine bereits hochgeladene Datei) oder `image_base64`
    muss gesetzt sein.
  fields:
    plant_id:
      name: Pflanzen-ID
      required: true
      selector:
        text:
    path:
      name: Pfad
      description: URL-Pfad zu einer bereits hochgeladenen Datei.
      selector:
        text:
    image_base64:
      name: Base64-Bild
      description: Alternative zu path; wird direkt hochgeladen.
      selector:
        text:
          multiline: true
    note:
      name: Notiz
      selector:
        text:
    taken_at:
      name: Aufnahmedatum
      description: Optional, Default ist jetzt.
      selector:
        datetime:

remove_plant_photo:
  name: Foto entfernen
  description: Entfernt ein Foto aus dem Verlauf einer Pflanze.
  fields:
    plant_id:
      name: Pflanzen-ID
      required: true
      selector:
        text:
    path:
      name: Pfad
      required: true
      selector:
        text:
    keep_file:
      name: Datei behalten
      description: Wenn aktiv, wird nur der Eintrag entfernt, die Datei aber nicht vom Disk gelöscht.
      default: false
      selector:
        boolean:
```

- [ ] **Step 3.5: Übersetzungen ergänzen**

In `strings.json`, `translations/en.json`, `translations/de.json` jeweils im `services`-Block analog `add_plant_photo` und `remove_plant_photo`-Einträge anlegen. Format wie bei den bestehenden Services. (Englisch in en.json, Deutsch in de.json/services.yaml.)

- [ ] **Step 3.6: Sanity + Commit**

```bash
python3 -m py_compile custom_components/plant_care/*.py && /tmp/pc-test/bin/python -m pytest tests/ -q | tail -3 && python3 -c "import json; [json.load(open(p)) for p in ['custom_components/plant_care/strings.json','custom_components/plant_care/translations/en.json','custom_components/plant_care/translations/de.json']]; print('JSON OK')"
```

```bash
git add custom_components/plant_care/
git commit -m "Services: add_plant_photo + remove_plant_photo

Beide Services nutzen einen gemeinsamen save_uploaded_photo-Helper
in http.py (Refactor: PlantPhotoUploadView delegiert dorthin).

i18n + services.yaml ergänzt.
"
```

---

### Task 4: Sensor-Attribut `photos_count`

**Files:**
- Modify: `custom_components/plant_care/sensor.py`

- [ ] **Step 4.1: Attribut ergänzen**

In `sensor.py`, in `extra_state_attributes` der `PlantSensor`-Klasse, das `return`-Dict ergänzen:

```python
            "photos": plant.get("photos", []),
            "photos_count": len(plant.get("photos") or []),
```

- [ ] **Step 4.2: Sanity + Commit**

```bash
python3 -m py_compile custom_components/plant_care/sensor.py && /tmp/pc-test/bin/python -m pytest tests/ -q | tail -3
```

```bash
git add custom_components/plant_care/sensor.py
git commit -m "Sensor: photos + photos_count Attribute"
```

---

### Task 5: Frontend Verlauf-Strip in Detail-View

**Files:**
- Modify: `custom_components/plant_care/frontend/plant-care-panel.js`

- [ ] **Step 5.1: `_renderPhotoHistory` einfügen**

Vor `_renderHistorySection(p)` einfügen:

```javascript
  _renderPhotoHistory(p) {
    const photos = Array.isArray(p.photos) ? p.photos : [];
    return `
      <section class="photo-history">
        <h3>📸 Foto-Verlauf (${photos.length})</h3>
        <div class="photo-actions">
          <button class="btn small" data-action="add-photo" data-id="${this._escapeAttr(p.plant_id)}">
            + Foto hinzufügen
          </button>
          <input type="file" accept="image/*" id="add-photo-input" style="display:none">
        </div>
        ${photos.length === 0 ? `
          <p class="muted small">Noch keine Fotos.</p>
        ` : `
          <div class="photo-strip">
            ${photos.map((ph, idx) => `
              <button class="photo-thumb" data-action="open-lightbox" data-id="${this._escapeAttr(p.plant_id)}" data-idx="${idx}">
                <img src="${this._escapeAttr(ph.path)}" alt="">
                <span class="photo-thumb-date">${this._escape(this._relativeTime(ph.taken_at))}</span>
              </button>
            `).join("")}
          </div>
        `}
      </section>
    `;
  }
```

- [ ] **Step 5.2: In Detail-View einbinden**

In `_renderDetail`, **nach** der `detail-grid`-Section und **vor** der `tips`-Section:

```javascript
        ${this._renderPhotoHistory(p)}
```

- [ ] **Step 5.3: CSS**

In `_styles`, am Ende:

```css
      .photo-history {
        margin-bottom: 20px;
      }
      .photo-history h3 {
        margin: 0 0 8px;
        font-size: 1rem;
      }
      .photo-actions {
        margin-bottom: 12px;
      }
      .photo-strip {
        display: flex;
        gap: 8px;
        overflow-x: auto;
        padding-bottom: 4px;
      }
      .photo-thumb {
        flex: 0 0 auto;
        width: 80px;
        background: none;
        border: 1px solid var(--divider-color, rgba(0,0,0,0.1));
        border-radius: 8px;
        padding: 4px;
        cursor: pointer;
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 4px;
      }
      .photo-thumb:hover {
        border-color: var(--sage);
      }
      .photo-thumb img {
        width: 70px;
        height: 70px;
        object-fit: cover;
        border-radius: 4px;
        display: block;
      }
      .photo-thumb-date {
        font-size: 0.7rem;
        color: var(--secondary-text-color, #777);
      }
```

- [ ] **Step 5.4: Click-Handler `add-photo`**

In `_onClick`, vor `case "photo-identify":`:

```javascript
      case "add-photo": {
        evt.preventDefault();
        const input = this.shadowRoot.getElementById("add-photo-input");
        const plantId = id;
        if (input) {
          input.onchange = (e) => {
            const file = e.target.files && e.target.files[0];
            if (file) this._handleAddPhotoFile(plantId, file);
          };
          input.click();
        }
        break;
      }
```

Und die zugehörige Methode (nach `_handlePhotoFile`):

```javascript
  async _handleAddPhotoFile(plantId, file) {
    if (!file || !file.type.startsWith("image/")) {
      this._showToast("error", "Bitte ein Bild auswählen");
      return;
    }
    this._aiBusy = true;
    this._render();
    try {
      const dataUrl = await this._resizeImage(file);
      const upload = await this._uploadPhotoToBackend(dataUrl);
      await this._callServiceWithResponse(
        "plant_care",
        "add_plant_photo",
        { plant_id: plantId, path: upload.path },
      );
      this._showToast("success", "Foto hinzugefügt");
    } catch (err) {
      console.error(err);
      this._showToast("error", err.message || String(err));
    } finally {
      this._aiBusy = false;
      this._render();
    }
  }
```

- [ ] **Step 5.5: Browser-Test + Commit**

1. Detail-View einer Pflanze öffnen → Verlauf-Sektion sichtbar
2. "+ Foto hinzufügen" → File-Picker → Bild auswählen → Toast + neues Thumb erscheint

```bash
git add custom_components/plant_care/frontend/plant-care-panel.js
git commit -m "Frontend: Foto-Verlauf-Strip in Detail-View

Horizontaler Strip mit Thumbnails (80px) + Datum-Label.
'+ Foto hinzufügen' nutzt die existierende Upload-Pipeline und
ruft danach plant_care.add_plant_photo auf.
"
```

---

### Task 6: Frontend Lightbox + Löschen

**Files:**
- Modify: `custom_components/plant_care/frontend/plant-care-panel.js`

- [ ] **Step 6.1: State**

Im Constructor:

```javascript
    this._lightbox = null;  // { plantId, idx } | null
```

In `_render`, im `sig`-Array zusätzlich:

```javascript
      JSON.stringify(this._lightbox || {}),
```

- [ ] **Step 6.2: `_renderLightbox`**

Nach `_renderPhotoHistory` einfügen:

```javascript
  _renderLightbox() {
    if (!this._lightbox) return "";
    const plant = this._plantById(this._lightbox.plantId);
    if (!plant) return "";
    const photos = Array.isArray(plant.photos) ? plant.photos : [];
    const idx = Math.max(0, Math.min(this._lightbox.idx, photos.length - 1));
    if (photos.length === 0) return "";
    const photo = photos[idx];
    const dateStr = photo.taken_at ? new Date(photo.taken_at).toLocaleString() : "";
    return `
      <div class="lightbox" data-action="lightbox-close">
        <div class="lightbox-content" data-stop>
          <header class="lightbox-header">
            <h3>${this._escape(plant.name)}</h3>
            <span class="muted small">${this._escape(dateStr)}</span>
            ${photo.note ? `<p class="muted small">${this._escape(photo.note)}</p>` : ""}
          </header>
          <div class="lightbox-image">
            <img src="${this._escapeAttr(photo.path)}" alt="">
          </div>
          <footer class="lightbox-footer">
            <button class="btn ghost" data-action="lightbox-prev" ${idx <= 0 ? "disabled" : ""}>← Älter</button>
            <button class="btn ghost" data-action="lightbox-next" ${idx >= photos.length - 1 ? "disabled" : ""}>Neuer →</button>
            <span class="lightbox-spacer"></span>
            <button class="btn danger small" data-action="lightbox-delete">Löschen</button>
            <button class="btn small" data-action="lightbox-close">Schließen</button>
          </footer>
        </div>
      </div>
    `;
  }
```

(Hinweis: `data-stop` ist nur ein Marker; Click-Handler ignoriert
inner clicks per `closest("[data-stop]")`-Check.)

- [ ] **Step 6.3: Im Render einbinden**

In `_render`, vor dem schließenden `</div>` des `.app`-Containers:

```javascript
        ${this._lightbox ? this._renderLightbox() : ""}
```

- [ ] **Step 6.4: Click-Handler**

In `_onClick`, im `switch`-Block:

```javascript
      case "open-lightbox":
        this._lightbox = { plantId: id, idx: parseInt(target.dataset.idx, 10) || 0 };
        this._setState({});
        break;
      case "lightbox-close":
        // Nur schließen wenn Klick außerhalb des content (oder explizit Close-Button)
        if (target.dataset.action === "lightbox-close" && evt.target.closest("[data-stop]")) {
          // Click im content – nur schließen wenn auf den Button selbst
          if (target.tagName !== "BUTTON") break;
        }
        this._lightbox = null;
        this._setState({});
        break;
      case "lightbox-prev":
        if (this._lightbox) {
          this._lightbox = { ...this._lightbox, idx: Math.max(0, this._lightbox.idx - 1) };
          this._setState({});
        }
        break;
      case "lightbox-next": {
        if (!this._lightbox) break;
        const plant = this._plantById(this._lightbox.plantId);
        const max = (plant?.photos?.length || 1) - 1;
        this._lightbox = { ...this._lightbox, idx: Math.min(max, this._lightbox.idx + 1) };
        this._setState({});
        break;
      }
      case "lightbox-delete": {
        if (!this._lightbox) break;
        const plant = this._plantById(this._lightbox.plantId);
        const photo = plant?.photos?.[this._lightbox.idx];
        if (!photo) break;
        if (!confirm("Foto wirklich löschen?")) break;
        this._callService("plant_care", "remove_plant_photo", {
          plant_id: this._lightbox.plantId,
          path: photo.path,
        }).then(() => {
          this._showToast("success", "Foto gelöscht");
          // Index anpassen wenn am Ende
          const newPlant = this._plantById(this._lightbox.plantId);
          const len = newPlant?.photos?.length || 0;
          if (len === 0) {
            this._lightbox = null;
          } else if (this._lightbox.idx >= len) {
            this._lightbox = { ...this._lightbox, idx: len - 1 };
          }
          this._setState({});
        }).catch((err) => {
          this._showToast("error", this._fmtErr(err));
        });
        break;
      }
```

- [ ] **Step 6.5: CSS**

In `_styles`, am Ende:

```css
      .lightbox {
        position: fixed;
        inset: 0;
        background: rgba(0,0,0,0.8);
        z-index: 100;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 16px;
      }
      .lightbox-content {
        background: var(--card-background-color, #fff);
        border-radius: 12px;
        max-width: 800px;
        max-height: 90vh;
        display: flex;
        flex-direction: column;
        overflow: hidden;
      }
      .lightbox-header {
        padding: 16px;
        border-bottom: 1px solid var(--divider-color, rgba(0,0,0,0.1));
      }
      .lightbox-header h3 { margin: 0 0 4px; }
      .lightbox-image {
        flex: 1 1 auto;
        display: flex;
        align-items: center;
        justify-content: center;
        background: #000;
        min-height: 200px;
      }
      .lightbox-image img {
        max-width: 100%;
        max-height: 60vh;
        object-fit: contain;
      }
      .lightbox-footer {
        padding: 12px 16px;
        display: flex;
        gap: 8px;
        align-items: center;
        flex-wrap: wrap;
      }
      .lightbox-spacer { flex: 1 1 auto; }
```

- [ ] **Step 6.6: Test + Commit**

1. Detail-View → Thumb tappen → Lightbox erscheint
2. ← / → navigieren funktioniert
3. Außerhalb klicken schließt Lightbox
4. "Löschen" → Confirm → Foto verschwindet, Thumb auch

```bash
git add custom_components/plant_care/frontend/plant-care-panel.js
git commit -m "Frontend: Lightbox mit Navigation und Löschen

Tap auf Thumbnail öffnet Lightbox mit großem Bild, Datum, Note.
← / → navigieren chronologisch durch die Fotos.
Löschen ruft plant_care.remove_plant_photo auf.
"
```

---

### Task 7: Frontend Compare-Mode

**Files:**
- Modify: `custom_components/plant_care/frontend/plant-care-panel.js`

- [ ] **Step 7.1: Compare-State**

Im Lightbox-State erweitern:

```javascript
    this._lightbox = null;  // { plantId, idx, compare?: { idxA, idxB } } | null
```

- [ ] **Step 7.2: Compare-View im Lightbox-Render**

Im `_renderLightbox`, **vor** dem `<div class="lightbox-image">`-Block, eine Verzweigung einbauen:

```javascript
    if (this._lightbox.compare) {
      const { idxA, idxB } = this._lightbox.compare;
      const a = photos[Math.max(0, Math.min(idxA, photos.length - 1))];
      const b = photos[Math.max(0, Math.min(idxB, photos.length - 1))];
      const optionsHtml = photos.map((ph, i) =>
        `<option value="${i}">${new Date(ph.taken_at).toLocaleDateString()}</option>`
      ).join("");
      return `
        <div class="lightbox" data-action="lightbox-close">
          <div class="lightbox-content lightbox-compare" data-stop>
            <header class="lightbox-header">
              <h3>${this._escape(plant.name)} – Vergleich</h3>
            </header>
            <div class="compare-grid">
              <div class="compare-slot">
                <select data-action="compare-set-a">
                  ${optionsHtml.replace(`value="${idxA}"`, `value="${idxA}" selected`)}
                </select>
                <img src="${this._escapeAttr(a.path)}" alt="">
              </div>
              <div class="compare-slot">
                <select data-action="compare-set-b">
                  ${optionsHtml.replace(`value="${idxB}"`, `value="${idxB}" selected`)}
                </select>
                <img src="${this._escapeAttr(b.path)}" alt="">
              </div>
            </div>
            <footer class="lightbox-footer">
              <button class="btn ghost" data-action="compare-exit">← Zurück</button>
              <span class="lightbox-spacer"></span>
              <button class="btn small" data-action="lightbox-close">Schließen</button>
            </footer>
          </div>
        </div>
      `;
    }
```

- [ ] **Step 7.3: "Vergleichen"-Button im Single-Lightbox-Footer**

In `_renderLightbox`, im Footer (nach dem `lightbox-next`-Button) den
"Vergleichen"-Button einfügen, **vor** dem Spacer:

```javascript
            <button class="btn small" data-action="compare-enter" ${photos.length < 2 ? "disabled" : ""}>Vergleichen</button>
            <span class="lightbox-spacer"></span>
```

- [ ] **Step 7.4: Click-Handler**

In `_onClick`:

```javascript
      case "compare-enter": {
        if (!this._lightbox) break;
        const plant = this._plantById(this._lightbox.plantId);
        const len = plant?.photos?.length || 0;
        if (len < 2) break;
        this._lightbox = {
          ...this._lightbox,
          compare: { idxA: 0, idxB: len - 1 },
        };
        this._setState({});
        break;
      }
      case "compare-exit":
        if (this._lightbox) {
          const next = { ...this._lightbox };
          delete next.compare;
          this._lightbox = next;
          this._setState({});
        }
        break;
```

Im `_onChange` ergänzen:

```javascript
    if (t.dataset && t.dataset.action === "compare-set-a") {
      this._lightbox = {
        ...this._lightbox,
        compare: { ...this._lightbox.compare, idxA: parseInt(t.value, 10) || 0 },
      };
      this._setState({});
      return;
    }
    if (t.dataset && t.dataset.action === "compare-set-b") {
      this._lightbox = {
        ...this._lightbox,
        compare: { ...this._lightbox.compare, idxB: parseInt(t.value, 10) || 0 },
      };
      this._setState({});
      return;
    }
```

(Hinweis: das `_onChange` ist nur am `<form>` registriert; für `<select>` außerhalb des Forms muss der Event-Listener auf den Shadow-Root erweitert werden. Falls das nicht trivial passt, ein onChange-Handler direkt im Lightbox-Render via inline data-Attribut + ein `change`-Listener im Render-Hook am Shadow-Root.)

Sicherer Pattern: in `_render` zusätzlich:

```javascript
    this.shadowRoot.querySelectorAll("[data-action='compare-set-a'], [data-action='compare-set-b']").forEach((el) => {
      el.addEventListener("change", this._onChange);
    });
```

direkt nach den existierenden Form-Event-Listenern.

- [ ] **Step 7.5: CSS**

```css
      .lightbox-compare { max-width: 1100px; }
      .compare-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 8px;
        padding: 12px;
      }
      .compare-slot {
        display: flex;
        flex-direction: column;
        gap: 8px;
      }
      .compare-slot img {
        width: 100%;
        height: 50vh;
        object-fit: contain;
        background: #000;
        border-radius: 6px;
      }
      .compare-slot select {
        padding: 6px;
        border-radius: 6px;
        border: 1px solid var(--divider-color, rgba(0,0,0,0.2));
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color);
      }
      @media (max-width: 700px) {
        .compare-grid { grid-template-columns: 1fr; }
        .compare-slot img { height: 30vh; }
      }
```

- [ ] **Step 7.6: Test + Commit**

1. Lightbox → "Vergleichen" → zwei Bilder side-by-side
2. Datum-Dropdown ändert das jeweilige Bild
3. "← Zurück" geht zurück zur Einzelansicht

```bash
git add custom_components/plant_care/frontend/plant-care-panel.js
git commit -m "Frontend: Compare-Mode im Lightbox

Side-by-Side-Vergleich von zwei Fotos mit Date-Dropdown pro Slot.
Default: neuestes + ältestes. Mobile: stack statt grid.
"
```

---

### Task 8: README + finaler Check

**Files:**
- Modify: `README.md`

- [ ] **Step 8.1: README-Sektion**

Nach "Mehrere Pflanzen gleichzeitig erledigen":

```markdown
### Foto-Verlauf

Im Detail-View einer Pflanze findest du den **📸 Foto-Verlauf** mit
allen jemals hinzugefügten Bildern. "+ Foto hinzufügen" lädt ein
neues Bild hoch und sortiert es nach Aufnahmedatum ein. Tap auf ein
Thumbnail öffnet die Lightbox; dort kannst du blättern, das Bild
löschen oder mit **Vergleichen** zwei Zeitpunkte nebeneinander
stellen ("vor 6 Monaten ↔ heute").

Cap pro Pflanze: 100 Fotos. Wird die Grenze überschritten, wird
das älteste Foto automatisch entfernt (Datei wird mitgelöscht).
```

- [ ] **Step 8.2: Final-Check**

```bash
python3 -m py_compile custom_components/plant_care/*.py && /tmp/pc-test/bin/python -m pytest tests/ -q | tail -3
```

Expected: alle Tests grün.

- [ ] **Step 8.3: Commit**

```bash
git add README.md
git commit -m "README: Foto-Verlauf Sektion"
```

---

## Self-Review

**Spec coverage:**
- Photos-Array-Schema → Task 1 (Helper) + Task 2 (Coordinator)
- Migration in async_load → Task 2.3
- add_plant_photo Service → Task 3.2
- remove_plant_photo Service → Task 3.2
- File-Delete bei remove_plant → Task 2.6
- save_uploaded_photo Refactor → Task 3.3
- photos_count Sensor-Attribut → Task 4.1
- Verlauf-Strip in Detail-View → Task 5
- Lightbox + Navigation + Delete → Task 6
- Compare-Mode → Task 7
- Cap 100 + älteste raus → Task 1.3 (`cap_photos`) + Task 2.5
- README → Task 8.1

**Placeholder scan:** Alle Code-Blöcke vollständig. ✓

**Type consistency:** `photos` ist überall `list[dict]` mit
`{path: str, taken_at: str, note: str}`. `async_add_plant_photo` returnt
`{path, index}`. `_lightbox` JS-State ist konsistent `{plantId, idx, compare?: {idxA, idxB}} | null`. ✓
