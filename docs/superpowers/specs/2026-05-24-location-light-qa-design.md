# Standort- und Licht-Q&A im Add-Flow — Design

**Status:** Approved (autonom)
**Date:** 2026-05-24
**Scope:** Sprint 6. Erweitert den "Pflanze hinzufügen"-Flow um zwei
Q&A-Fragen (Standort/Raum + Licht-Level) und reichert die KI-Vorschläge
um Standort-Tipps + Eignungs-Warnung an. Fokus Indoor.

## Ziel

Beim Anlegen einer Pflanze fragt das Panel zwei Kontext-Informationen
zusätzlich zum Namen ab: **Raum** (strukturiert) und **Lichtintensität**
(strukturiert). Beide fließen in den KI-Prompt ein, damit Spezies-
passende Gieß-/Düngeintervalle herauskommen und die KI Standort-
spezifische Tipps + ggf. eine Eignungs-Warnung liefert ("Sansevieria im
dunklen Bad: Sukkulente mag's eher trocken und hell, ungeeignet").

## Nicht-Ziele

- Outdoor-spezifische Fragen (Frosthärte, Wind, Regen) — kommen mit
  späterem Wetter-Feature.
- Multi-Step-Wizard. Alles bleibt im bestehenden Single-Page-Form,
  zusätzliche Felder über dem KI-Button.
- Eigener Multiplier-Code für Licht-Level. Die KI rechnet die Intervalle
  selbst aus, damit kein Konflikt mit dem späteren Seasonal-Feature
  entsteht.
- Bestehende `location`-Freitext-Feld wegrationalisieren. Das bleibt für
  konkrete Position-Beschreibung ("Fensterbank Nord").

## Datenmodell

Plant-Dict bekommt **vier** neue Felder:

```python
"light_level": "hell",                       # vollsonne | hell | halbschatten | schatten | ""
"room_type": "wohnzimmer",                   # structured oder ""
"location_tips": "Vermeide Mittagssonne",    # str, von KI gefüllt
"suitability_warning": "",                   # str, leer = passt
```

Migration in `async_load` per `plant.setdefault("...", "")` für alle vier
(idempotent, keine Storage-Version-Erhöhung).

Bestehendes `location` (Freitext) bleibt unverändert nutzbar als
"Detailangabe" ("Fensterbank Nord, links neben dem Sofa").

## Konstanten

In `const.py`:

```python
LIGHT_LEVELS: Final = ("vollsonne", "hell", "halbschatten", "schatten")
ROOM_TYPES: Final = (
    "wohnzimmer", "schlafzimmer", "kueche", "bad",
    "buero", "flur", "kinderzimmer",
)
```

Label-Mapping bleibt im Frontend (UI-Strings), damit die Konstanten
i18n-frei sind.

## KI-Prompt-Erweiterung

### `_aiSuggestFromName` (Name-only)

Vorher:

> Du bist Botaniker. Für die Zimmerpflanze "X": Gib Spezies, deutschen
> Trivialnamen, empfohlene Gieß-/Düngeintervalle in Tagen sowie kurze
> Pflegetipps zurück.

Nachher (wenn Q&A-Antworten vorhanden):

> Du bist Botaniker. Für die Zimmerpflanze "X":
> - Standort: {room_label or "nicht angegeben"}
> - Lichtintensität: {light_label or "nicht angegeben"}
>
> Gib zurück:
> - Spezies (botanisch), deutscher Trivialname
> - Gieß-/Düngeintervalle in Tagen, **passend zum genannten Licht-Level**
>   (bei wenig Licht seltener, bei Vollsonne öfter)
> - Allgemeine Pflegetipps
> - Standort-spezifische Tipps (was ist beim genannten Raum + Licht zu
>   beachten?)
> - Wenn der genannte Standort für diese Art ungeeignet ist: kurze
>   Begründung. Sonst leeres Feld.
> Antworte ausschließlich im vorgegebenen JSON-Schema.

### `_aiIdentifyFromPhoto` (Foto-Identify)

Analog: gleicher Block "Standort/Licht" wird in die `instructions`
angehängt. JSON-Schema kriegt die zwei zusätzlichen Felder.

### Erweitertes JSON-Schema

```js
{
  species: { selector: { text: {} } },
  common_name: { selector: { text: {} } },
  water_days: { selector: { number: { min: 1, max: 90 } } },
  fertilize_days: { selector: { number: { min: 1, max: 180 } } },
  tips: { selector: { text: { multiline: true } } },
  location_tips: { selector: { text: { multiline: true } } },       // NEU
  suitability_warning: { selector: { text: { multiline: true } } }, // NEU
  // (im Identify-Flow zusätzlich noch confidence wie bisher)
}
```

Die KI darf `location_tips`/`suitability_warning` leer lassen – Frontend
zeigt dann einfach nichts an.

## Frontend

### Add/Edit-Form (KI-Tab)

Zwischen dem `Name`-Feld und dem `✨ KI-Vorschlag`-Button:

```
📍 Standort                                  ☀ Licht
[Wohnzimmer ▾]                               ( ) Vollsonne (Südfenster)
                                             (●) Hell (am Fenster, nicht direkt)
                                             ( ) Halbschatten (1-2m vom Fenster)
                                             ( ) Schatten (weit vom Fenster)
                                             ( ) Weiß nicht
```

- Room-Dropdown: 7 Standardwerte + Option "Andere…" → blendet ein
  Freitext-Feld ein, dessen Wert dann in `room_type` landet.
- Licht-Radio-Group: 4 Werte + "Weiß nicht" (= leer)

Beim KI-Klick werden die aktuellen Werte aus dem Draft mit in den Prompt
gegeben. Sind beide leer, läuft der Prompt wie vor diesem Sprint.

Nach KI-Antwort:
- Felder `species`/`common_name`/`water_days`/`fertilize_days`/`tips`
  werden wie bisher in den Draft gemerged.
- `location_tips` und `suitability_warning` werden im Draft gespeichert
  und in einem **Info-Bereich unter dem KI-Button** angezeigt:

```
┌─ KI-Vorschlag ────────────────────────────┐
│ ✓ Vorschlag übernommen                    │
│                                           │
│ 💡 Standort-Tipps                         │
│ Monstera mag indirektes, helles Licht.    │
│ Wohnzimmer ist gut, aber vermeide direkte │
│ Mittagssonne.                             │
└───────────────────────────────────────────┘
```

Falls `suitability_warning` nicht leer:

```
┌─ ⚠ Achtung ───────────────────────────────┐
│ Diese Sukkulente mag's eher trocken. Bad  │
│ ist meist zu feucht – Schlafzimmer oder   │
│ Wohnzimmer wäre besser.                   │
│                                           │
│              [Trotzdem speichern]         │
└───────────────────────────────────────────┘
```

Keine Hard-Block-Validation – User darf trotzdem speichern.

### Edit-Form

Dieselben zwei Felder, vorausgefüllt aus `room_type` + `light_level`.
Wenn der User die Felder ändert, **wird die KI nicht automatisch
re-evaluiert**. Erst manueller `✨ KI-Vorschlag`-Klick triggert neue
Auswertung (verwendet die neuen Werte).

### Detail-View

Neue Sektion `.location-section` zwischen `detail-grid` und
`tips` (existing), nur sichtbar wenn `room_type` ODER `light_level`
gesetzt sind:

```
📍 Standort
Raum: Wohnzimmer · Licht: Hell · Position: Fensterbank Nord

💡 Standort-Tipps
Vermeide Mittagssonne. Im Winter darf sie näher ans Fenster.
```

Wenn `suitability_warning` nicht leer: oranges Banner **ganz oben** im
Detail-View, vor `detail-header`:

```
⚠ Diese Sukkulente mag's eher trocken …  [✕]
```

Das `✕` ruft `plant_care.update_plant` mit `suitability_warning: ""`
auf → Banner verschwindet dauerhaft (Plant bleibt unverändert sonst).

## Sensor

Vier neue Attribute auf `PlantSensor`:

```python
"light_level": plant.get("light_level", ""),
"room_type": plant.get("room_type", ""),
"location_tips": plant.get("location_tips", ""),
"suitability_warning": plant.get("suitability_warning", ""),
```

Für Lovelace-Templates oder externe Card-Custom-Logik nutzbar.

## Service-Schema

`ADD_PLANT_SCHEMA` und `UPDATE_PLANT_SCHEMA` in `__init__.py` jeweils:

```python
        vol.Optional("light_level"): vol.In(["", *LIGHT_LEVELS]),
        vol.Optional("room_type"): cv.string,         # akzeptiert Standard oder freier String
        vol.Optional("location_tips"): cv.string,
        vol.Optional("suitability_warning"): cv.string,
```

`services.yaml` + i18n entsprechend mit den neuen Feldern erweitern.

## Edge Cases

| Fall | Verhalten |
|---|---|
| User füllt Q&A nicht aus, klickt nur KI | Prompt enthält "nicht angegeben" → KI gibt allgemeine Empfehlung wie heute |
| User wählt "Andere…" Room | Freitext-Wert wird als `room_type` gespeichert; Dropdown-Position später als "Andere" wiedergegeben + freitext sichtbar |
| AI lässt `location_tips` leer | Info-Block wird nicht gerendert (keine leere Sektion) |
| AI gibt unsinnige Warning ("Pflanze stirbt!") | User klickt `✕` → leer, dauerhaft weg |
| User ändert nur Light im Edit-Form, kein KI-Klick | Light wird gespeichert. Intervalle bleiben wie bisher. Sensor-Attribute aktualisiert |
| Library-Pick mit preferred_light | Frontend zeigt Hint-Banner wenn User-Light davon abweicht. Out-of-scope für Sprint 6 (kommt mit Library-Schema-Update separat) |
| Translation für Room-Labels | Frontend-only, DE-Labels (Panel ist DE-only) |
| API-Response enthält keine neuen Felder (alte AI-Version) | Fields bleiben leer, kein Crash |

## Dateien

| Datei | Änderung |
|---|---|
| `const.py` | + `LIGHT_LEVELS`, `ROOM_TYPES` |
| `coordinator.py` | + Migration für 4 neue Felder in `async_load`; im `async_add_plant` die Felder ins Plant-Dict aufnehmen |
| `__init__.py` | + Schema-Erweiterung `ADD_PLANT_SCHEMA` + `UPDATE_PLANT_SCHEMA` |
| `services.yaml` | + 4 neue Feld-Definitionen pro Service (Optional) |
| `strings.json` + de.json + en.json | + i18n |
| `sensor.py` | + 4 neue Attribute |
| `frontend/plant-care-panel.js` | + Q&A-UI im Form, KI-Prompts angepasst, Detail-View-Sektion, Warning-Banner, Dismiss-Action |
| `README.md` | + kurze Sektion "Standort-Q&A" |

## Risiken

- **AI-Halluzination bei Warning:** Eine schlecht formulierte Warnung
  könnte den User verunsichern. Mitigation: Dismiss-Button (✕), klare
  Sprache im Prompt ("kurze Begründung"), Warning-Feld darf leer sein.
- **Q&A-Lähmung:** User klickt "✨ KI-Vorschlag" ohne Q&A auszufüllen.
  Mitigation: alle Felder optional, alter Prompt-Pfad bleibt funktional.
- **Inkonsistenz Light↔Intervalle:** User ändert nur Light später, KI
  wird nicht automatisch re-getriggered. Mitigation: explizit
  dokumentiert ("Bei Umzug: KI-Vorschlag erneut tippen"). Auto-Re-Eval
  wäre teuer (AI-Cost) und überraschend.

## Aufwand

Geschätzt 3-4h:
- Schema + Migration + Konstanten: ~30 min
- Service-Schemas + services.yaml + i18n: ~30 min
- KI-Prompts (suggest + identify): ~30 min
- Form-UI (Dropdown + Radios + Andere-Fallback): ~45 min
- Detail-View-Sektion + Warning-Banner: ~45 min
- Sensor-Attribute + Edit-Form Vorbelegung: ~15 min
- README + manueller Test: ~30 min

Keine neuen pytest-Pure-Helper, weil keine eigene Multiplier-Logik
implementiert wird (die KI rechnet selbst).
