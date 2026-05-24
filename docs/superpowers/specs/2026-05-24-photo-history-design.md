# Foto-Verlauf / Growth Tracker — Design

**Status:** Approved (autonom)
**Date:** 2026-05-24
**Scope:** Sprint 3 von 5. Verändert das Plant-Schema (Storage-Migration nötig).

## Ziel

Pro Pflanze mehrere datierte Fotos statt nur eins. Detail-View zeigt
einen scrollbaren Verlauf-Strip; Lightbox für volle Ansicht; Side-by-
Side-Vergleich von zwei Zeitpunkten ("vor 6 Monaten ↔ heute").

## Nicht-Ziele

- Automatische Wachstumsmessung (Höhe, Blätter etc.). Bilder werden
  ohne Auswertung gespeichert.
- Video.
- Foto-Editing (Crop, Filter). User bringt seine eigenen Fotos.
- Cloud-Sync / externes Backup. Nur lokal in HA-Media.

## Datenmodell

Bestehendes Plant-Dict bekommt ein neues Array-Feld:

```python
{
  ...
  "photo": "/api/plant_care/photos/abc.jpg",  # Primärfoto (= photos[0].path)
  "photos": [
    {
      "path": "/api/plant_care/photos/abc.jpg",
      "taken_at": "2026-05-24T10:30:00+00:00",
      "note": ""  # optional, Default leer
    },
    {
      "path": "/api/plant_care/photos/def.jpg",
      "taken_at": "2026-03-12T14:00:00+00:00",
      "note": "nach Umtopfen"
    }
  ]
}
```

Sortierung im Array: **descending nach `taken_at`** (neuestes zuerst).
Das `photo`-Top-Level-Feld bleibt erhalten und enthält immer
`photos[0].path` – Backwards-Compat für Lovelace-Karte und Sensor-
Attribute, die `photo` direkt lesen.

### Migration (async_load)

Wenn `photos` fehlt:
- Falls `photo` vorhanden und nicht leer: `photos = [{path: photo, taken_at: created or now, note: ""}]`
- Sonst: `photos = []`

Storage-Version bleibt `1`; Migration ist additiv (alte Felder bleiben
lesbar). Beim ersten Save wird das `photos`-Array persistiert.

## Services

### `plant_care.add_plant_photo`

Fügt ein Foto hinzu. Akzeptiert entweder einen `path` (wenn der User
schon hochgeladen hat) oder ein `image_base64` (für die übliche
Upload-Pipeline).

| Feld | Typ | Required | Beschreibung |
|---|---|---|---|
| `plant_id` | string | ja | – |
| `path` | string | nein | Pfad zu bereits hochgeladenem Foto |
| `image_base64` | string | nein | Alternativ: Base64-Daten zum Upload |
| `note` | string | nein | Freitext-Notiz |
| `taken_at` | datetime | nein | Default: jetzt |

Genau **eines** von `path` / `image_base64` muss gesetzt sein.

Verhalten:
1. Validate inputs
2. Bei `image_base64`: über die bestehende `PlantPhotoUploadView`-Logik
   zur Datei machen (Refactor: gemeinsame Helper-Funktion)
3. Coordinator append zur `photos`-Liste, sortiert neu, setzt `photo`
   auf `photos[0].path`
4. Persist + Dispatcher-Signal `SIGNAL_PLANTS_UPDATED`

Response: `{path: "<resolved-path>", index: 0}`.

### `plant_care.remove_plant_photo`

Entfernt ein Foto aus dem Verlauf und (optional) auch die Datei.

| Feld | Typ | Required | Beschreibung |
|---|---|---|---|
| `plant_id` | string | ja | – |
| `path` | string | ja | exakter Pfad-String aus `photos[*].path` |
| `keep_file` | bool | nein | Default `false` → File wird vom Disk gelöscht |

Wenn `path` = `photos[0]` (Primärfoto): nach Entfernen wird `photo` auf
`photos[0].path` aktualisiert oder leer wenn keine mehr da sind.

Datei-Delete läuft via `hass.async_add_executor_job` – pro File ein
Best-Effort `unlink(missing_ok=True)`.

## Frontend

### Detail-View Verlauf-Sektion

In der Detail-View, **nach** der `detail-grid` (mit Wasser/Dünger/
Moisture) und **vor** der `.tips`-Sektion, neue Sektion `.photo-history`:

```
┌────────────────────────────┐
│ 📸 Foto-Verlauf (4)       │
│ [+ Foto hinzufügen]        │
│                            │
│ ┌──┐ ┌──┐ ┌──┐ ┌──┐ →     │
│ │  │ │  │ │  │ │  │       │
│ └──┘ └──┘ └──┘ └──┘       │
│ heute  -2W  -1M  -6M       │
└────────────────────────────┘
```

- Horizontaler Strip mit Thumbnails (60×60 px), neuestes links
- Datum-Label unter jedem Thumb (relativeTime)
- Tap auf Thumb → Lightbox

### Lightbox / Foto-Viewer

Vollbild-Overlay mit:
- Großes Bild, contain-fit
- Header: Pflanzenname + Datum (absolut) + Note (wenn vorhanden)
- Footer: "← Vorheriges" / "Nächstes →" / "Vergleichen" / "Löschen"
- Tap außerhalb / ESC schließt

### Compare-Mode

In Lightbox auf "Vergleichen" tap → zwei Slots side-by-side. Jeder Slot
hat einen Date-Picker (Dropdown über alle vorhandenen `taken_at`-Werte).
Default: Slot A = neuestes, Slot B = ältestes.

```
┌──────────────────┬──────────────────┐
│  [neuestes ▼]    │  [ältestes ▼]    │
│                  │                  │
│   großes Bild    │   großes Bild    │
│                  │                  │
│   heute          │   vor 6 Monaten  │
└──────────────────┴──────────────────┘
```

### "+ Foto hinzufügen"

Tap → File-Picker → analog zur bestehenden Upload-Pipeline
(`_resizeImage` + `_uploadPhotoToBackend`). Nach Upload wird
`plant_care.add_plant_photo` mit `path` aufgerufen. Optional Modal
für Note-Eingabe vor dem Hinzufügen (Default: keine Note, Click "Speichern").

## Sensor-Attribute

Neues optionales Attribut `photos_count` auf `PlantSensor`. Lovelace
oder Templates können das nutzen.

## Edge Cases

| Fall | Verhalten |
|---|---|
| Pflanze hat keine Fotos (nach Migration leer) | Verlauf-Sektion zeigt nur "+ Foto hinzufügen" + Hint "Noch keine Fotos" |
| User löscht das einzig vorhandene Foto | `photo = ""`, `photos = []`. Detail-View zeigt Platzhalter-Icon wie bisher |
| User löscht Primärfoto bei 3+ Fotos | `photo` wird automatisch auf neues `photos[0].path` aktualisiert |
| File auf Disk fehlt, aber im `photos`-Array drin (manuell gelöscht) | `<img>` zeigt Broken-Image. Beim nächsten User-Löschvorgang: `unlink(missing_ok=True)` → kein Fehler |
| Cap-Limit? | Soft-Limit 100 Fotos pro Pflanze. Bei add_plant_photo: wenn `len(photos) >= 100` → ältestes Foto wird verworfen (File-Delete inklusive) |
| Pflanze wird gelöscht | Bestehende `async_remove_plant` löscht nur den DB-Eintrag, nicht die Foto-Files. **Neue Verhalten:** alle Files in `photos[*].path` werden ebenfalls vom Disk gelöscht |
| Migration: `photo` war `data:image/...`-URL | Greift die bestehende data-URL-Migration zuerst (in async_load), dann Photo-Array-Migration. Path wird korrekt übernommen. |

## Tests

Neue Pure-Helper:

```python
def sort_photos(photos: list[dict]) -> list[dict]:
    """Sortiert nach taken_at desc, Plant ohne taken_at landet hinten."""

def migrate_legacy_photo(plant: dict) -> bool:
    """Wenn 'photos' fehlt aber 'photo' existiert, baue Array.
    Returns True wenn migriert."""

def cap_photos(photos: list[dict], max_count: int) -> tuple[list[dict], list[dict]]:
    """Returns (kept, removed). removed = älteste über max_count."""
```

Tests pro Helper:
- `sort_photos`: leere Liste, ein Element, mehrere, mit/ohne taken_at
- `migrate_legacy_photo`: kein photo, leer-string photo, valid path photo,
  bereits migriert
- `cap_photos`: unter Cap, exakt am Cap, drüber

Coverage-Ziel: ~10 neue Tests.

## Dateien

| Datei | Änderung |
|---|---|
| `_utils.py` | + `sort_photos`, `migrate_legacy_photo`, `cap_photos` |
| `const.py` | + `MAX_PHOTOS_PER_PLANT = 100` |
| `coordinator.py` | + `async_add_plant_photo`, `async_remove_plant_photo`; Migration in async_load; File-Delete in async_remove_plant; `photo`-Sync auf `photos[0]` |
| `http.py` | + gemeinsamer Upload-Helper für add_plant_photo (refactor) |
| `sensor.py` | + `photos_count` Attribut |
| `__init__.py` | + 2 neue Services registrieren |
| `services.yaml` | + 2 neue Service-Definitionen |
| `strings.json`, `translations/de.json`, `translations/en.json` | + 2 neue Service-Strings |
| `frontend/plant-care-panel.js` | + Verlauf-Sektion, Lightbox-Render, Compare-Mode |
| `tests/test_utils.py` | + ~10 neue Tests |
| `README.md` | + Foto-Verlauf-Sektion |

## Risiken

- **Storage-Bloat:** Bei aktiven Usern mit vielen Pflanzen können Photo-
  Files schnell mehrere GB belegen. Mitigation: Cap auf 100 pro Pflanze,
  Resize-Limit 600px (bereits in `_resizeImage`).
- **Migration auf alten Storage:** Tests müssen bestätigen, dass
  migrate_legacy_photo idempotent ist (zweiter Aufruf hat keinen Effekt).
- **Frontend-Komplexität:** Lightbox + Compare ist nicht trivial in
  Vanilla-JS. Plan-Tasks halten die Komponenten klein.

## Aufwand

Geschätzt 6-8 h: Datenmodell + Migration + Helper (~2 h), Backend-
Services + Refactor (~1.5 h), Frontend Verlauf-Strip (~1 h), Frontend
Lightbox (~1.5 h), Frontend Compare (~1 h), manueller Test + Doku (~1 h).
