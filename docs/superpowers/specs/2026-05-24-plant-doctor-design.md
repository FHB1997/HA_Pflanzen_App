# Pflanzen-Sprechstunde (Disease/Pest Diagnose) — Design

**Status:** Approved (autonom)
**Date:** 2026-05-24
**Scope:** Sprint 4 von 5. Baut auf Foto-Verlauf-Schema auf, ergänzt Treatment-Tracking.

## Ziel

Wenn eine Pflanze auffällig aussieht (gelbe Blätter, Schädlinge, Pilz),
Foto aufnehmen → AI diagnostiziert → schlägt Behandlung vor → Plant
Care loggt die Behandlung mit Foto + Diagnose + Wiedervorlage-Datum.
Der User wird zur Wiedervorlage erinnert ("Treatment-Check fällig").

## Nicht-Ziele

- Eigene ML-Modelle. AI läuft über das bestehende `ai_task`-Pattern.
- Pflanzenarzt-Versprechen. Diagnosen sind Hilfestellung, nicht Diagnose.
- Bot-Style-Chat-Interface. Strukturierte Single-Shot-Auswertung.
- Behandlungsmittel-Bestellungen / E-Commerce.

## Datenmodell

Neues Plant-Dict-Feld `treatments: list[dict]`:

```python
{
  "treatments": [
    {
      "id": "uuid-hex-12",
      "started_at": "2026-05-24T10:00:00+00:00",
      "photo_path": "/api/plant_care/photos/abc.jpg",  # zugehöriges Foto
      "diagnosis": "Spinnmilben befallen die Unterseite der Blätter",
      "confidence": 0.78,                              # 0..1
      "treatment_steps": [
        "Pflanze unter lauwarmer Dusche abspülen",
        "Mit Neemöl-Lösung besprühen",
        "Luftfeuchtigkeit erhöhen (Hydrokultur-Schale)"
      ],
      "follow_up_days": 7,
      "follow_up_at": "2026-05-31T10:00:00+00:00",      # = started_at + follow_up_days
      "status": "open",                                 # "open" | "resolved" | "dismissed"
      "resolved_at": null
    }
  ]
}
```

Wird per `setdefault("treatments", [])` in `async_load` migriert
(idempotent, kein Storage-Version-Bump).

## AI-Integration

Nutzt `ai_task.generate_data` mit folgendem Schema:

```python
{
  "diagnosis": { "selector": { "text": { "multiline": True } } },
  "confidence": { "selector": { "number": { "min": 0, "max": 1 } } },
  "treatment_steps": { "selector": { "object": {} } },  # list[str]
  "follow_up_days": { "selector": { "number": { "min": 1, "max": 30 } } },
  "severity": { "selector": { "select": { "options": ["low", "medium", "high"] } } }
}
```

Prompt (DE, da Panel ist DE-only):

> Du bist erfahrener Botaniker und Pflanzenarzt. Auf dem angehängten Foto
> ist eine Pflanze, die ungewöhnlich aussieht. Analysiere:
> 1. Was siehst du? (Symptome)
> 2. Wahrscheinlichste Ursache (Schädling, Krankheit, Pflegefehler)
> 3. Konkrete Behandlungsschritte
> 4. Wann sollte man nachschauen ob die Behandlung wirkt?
>
> Antworte ausschließlich im vorgegebenen JSON-Schema. Treatment-Steps
> als Array von kurzen, konkreten Aktionen. Wenn die Pflanze gesund
> aussieht: diagnosis="Keine Auffälligkeiten erkannt", confidence < 0.5.

Optional: Plantenname + Spezies als Kontext mitgeben, damit die AI
arten-spezifische Hinweise gibt.

## Services

### `plant_care.diagnose_plant`

| Feld | Typ | Required | Beschreibung |
|---|---|---|---|
| `plant_id` | string | ja | – |
| `path` | string | nein | Pfad zu Foto. Wenn fehlt, wird `photos[0]` der Pflanze genommen |
| `image_base64` | string | nein | Alternativ Upload + Diagnose in einem Call |

Verhalten:
1. Foto auflösen (Path oder Upload)
2. `ai_task.generate_data` aufrufen
3. Treatment-Eintrag bauen, an `treatments` anhängen
4. Auch zu `photos` hinzufügen (mit Note "Diagnose: <kurz>")
5. Persist + Signal

Response: das eingefügte Treatment-Objekt.

### `plant_care.resolve_treatment`

Markiert eine offene Behandlung als abgeschlossen.

| Feld | Typ | Required |
|---|---|---|
| `plant_id` | string | ja |
| `treatment_id` | string | ja |
| `outcome` | string-enum | nein, default `resolved` (`resolved` / `dismissed`) |

## Sensor-Integration

Status-String bekommt einen neuen Wert: `needs_attention` (höchste
Priorität). Logik:

```python
if any_open_treatment_overdue():
    return STATUS_NEEDS_ATTENTION
# bestehende Logik (needs_both / needs_water / needs_fertilizer / ok)
```

"overdue" = `follow_up_at <= now AND status == "open"`. Solange das
Treatment nicht resolved/dismissed ist und das Datum erreicht, signalisiert
der Sensor Aufmerksamkeitsbedarf.

Neues Status-Label im Frontend:
- `needs_attention` → "🔍 Treatment-Check fällig"
- Eigene Farbe (warnend, z.B. orange)

Erweiterte Sensor-Attribute:
- `open_treatments_count`: int
- `latest_treatment`: das jüngste Treatment-Objekt (oder None)

## Reminder-Integration

Die bestehende `evaluate_reminders` berücksichtigt jetzt auch
`needs_attention`. Die Action-Buttons in der HA-Mobile-App-Notification
sind dann andere:

- `needs_attention` → Buttons "✓ Erledigt" / "✗ Verwerfen" / "💤 Snooze 1d"

Action-IDs: `PLANTCARE_RESOLVE_<plant_id>_<treatment_id>` und
`PLANTCARE_DISMISS_<plant_id>_<treatment_id>`. Der Event-Handler in
`__init__.py` parst `parse_action_id` und routet zu
`coord.async_resolve_treatment`.

`parse_action_id` muss tolerant gegenüber dem Format mit zwei IDs sein.
Vorschlag: Action-Format `PLANTCARE_RESOLVE_<plant_id>_<treatment_id>`,
Parser splittet weiterhin nach max 3 Teilen → action="RESOLVE",
rest="<plant_id>_<treatment_id>". Im Handler dann nochmal splitten.

## Frontend

### Detail-View Erweiterung

Neue Sektion `.treatments` zwischen `detail-grid` und `photo-history`:

```
┌──────────────────────────┐
│ 🔍 Behandlungen          │
│ [+ Was ist los?]         │
│                          │
│ ⚠ Offen seit 3 Tagen     │
│   "Spinnmilben"          │
│   Fällig: morgen         │
│   [✓ Erledigt] [✗ ...]  │
│                          │
│ ✓ Vor 2 Monaten          │
│   "Wurzelfäule"          │
│   abgeschlossen          │
└──────────────────────────┘
```

### Diagnose-Flow

Tap auf "+ Was ist los?":
1. Modal mit File-Picker + "Vorhandenes Foto" (aus photos[])
2. Upload + AI-Call (Spinner, kann 5-15s dauern)
3. Ergebnis-Modal: Diagnose-Text + Steps + Confidence-Bar
4. Buttons: "✓ Speichern und merken" (Default) / "Verwerfen"
5. Bei Speichern: Treatment angelegt, Detail-View aktualisiert

### Resolve-Flow

In der Treatments-Liste pro offenes Treatment ein "✓ Erledigt"-Button.
Tap → ruft `plant_care.resolve_treatment` auf, Eintrag wird grün
("✓ Vor 5 Tagen abgeschlossen").

## Edge Cases

| Fall | Verhalten |
|---|---|
| AI antwortet "keine Auffälligkeiten" (Confidence < 0.5) | Frontend zeigt grünen Hinweis "Sieht gesund aus!" und legt **kein** Treatment an |
| AI ist nicht eingerichtet | Button disabled, Toast bei Klick |
| Mehrere offene Treatments parallel | Status bleibt `needs_attention` bis alle resolved/dismissed; Sensor-Attribut listet alle |
| Photo der Pflanze gelöscht während Treatment offen | Treatment behält `photo_path`-String; <img> zeigt Broken-Image |
| Treatment-Item ohne ID (alte Daten) | Bei Migration: `setdefault("id", uuid.uuid4().hex[:12])` |
| User triggert AI 5x hintereinander auf gleicher Pflanze | Pro Aufruf neues Treatment → spammy. Mitigation: Backend ignoriert Anfragen wenn das letzte Treatment < 60s alt ist (Soft-Throttle) |

## Tests

Pure Helper in `_utils.py`:

```python
def has_overdue_treatment(treatments: list[dict], now: datetime) -> bool:
    """True wenn mindestens ein offenes Treatment fällig ist."""

def filter_open_treatments(treatments: list[dict]) -> list[dict]:
    """Liefert nur status='open' Treatments."""

def parse_treatment_action_id(action_id: str) -> tuple[str, str, str] | None:
    """PLANTCARE_RESOLVE_<plant_id>_<treatment_id> → (action, plant_id, treatment_id)."""
```

~10 neue Tests insgesamt.

## Dateien

| Datei | Änderung |
|---|---|
| `_utils.py` | + 3 neue Helper |
| `const.py` | + `STATUS_NEEDS_ATTENTION`, `SERVICE_DIAGNOSE_PLANT`, `SERVICE_RESOLVE_TREATMENT`, `MIN_DIAGNOSE_INTERVAL_SECONDS=60` |
| `coordinator.py` | + `async_diagnose_plant`, `async_resolve_treatment`; treatments-Migration |
| `sensor.py` | + `needs_attention` Status-Berechnung; neue Attribute |
| `http.py` | (keine direkte Änderung) |
| `__init__.py` | + 2 neue Services; Event-Handler erweitern für RESOLVE/DISMISS-Actions |
| `services.yaml` | + 2 Service-Definitionen |
| `strings.json` + translations | + i18n |
| `frontend/plant-care-panel.js` | + Treatment-Sektion + Diagnose-Modal + Resolve-Flow |
| `tests/test_utils.py` | + ~10 Tests |
| `README.md` | + Sprechstunde-Sektion |

## Risiken

- **AI-Halluzination:** AI könnte falsche Diagnosen liefern. Mitigation:
  Confidence-Anzeige im UI; im Prompt explizit "Wenn unsicher, sag es".
- **AI-Cost/Latency:** Foto + AI-Call kann 5-15s + Tokens kosten.
  Mitigation: nur User-initiiert, kein Auto-Scan.
- **Treatment-Spam:** User klickt Diagnose 10x. Soft-Throttle (60s).

## Aufwand

Geschätzt 5-7 h: Helper + Tests (~1 h), Coordinator-Methoden + Migration
(~1.5 h), Services + i18n (~1 h), Sensor-Status-Erweiterung (~30 min),
Frontend-Modal + Treatments-Sektion (~2 h), README + Test (~1 h).
