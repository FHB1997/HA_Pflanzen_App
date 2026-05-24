# Bulk-Actions — Design

**Status:** Approved (autonom; siehe `feedback-autonomous-flow` Memory)
**Date:** 2026-05-24
**Scope:** Sprint 2 von 5 nach Feature-Brainstorming.

## Ziel

Im Sidebar-Panel mehrere Pflanzen gleichzeitig auswählen und als
"gegossen" oder "gedüngt" markieren – ohne pro Pflanze in die Detail-View
zu springen.

Use-Case: Sonntagsrundgang. User hat 15 Pflanzen, gießt alle in einem
Schwung, will das mit 3 Klicks abhaken statt 15-mal je 3 Taps.

## Nicht-Ziele

- Bulk-Delete (zu gefährlich für eine UI-Funktion).
- Bulk-Edit (Spezies/Intervalle ändern). Zu viele Edge-Cases.
- Bulk-Snooze. Snooze ist notification-bezogen, kein Pflege-Akt.
- Eigener Backend-Service. Vorhandene `water_plant` / `fertilize_plant`
  werden parallel aufgerufen – einfacher als ein neuer Sammel-Service.

## UX

### Bulk-Mode-Toggle

In der Topbar der List-View neben "+ Neue Pflanze" erscheint ein
zweiter Button "☑ Auswahl". Tap aktiviert Bulk-Mode:

- Plant-Cards bekommen einen Checkbox-Overlay (top-left)
- Topbar zeigt "Abbrechen"-Button statt "+ Neue Pflanze"
- Sticky-Bottom-Bar erscheint (siehe unten)

### Bottom-Action-Bar (sichtbar nur in Bulk-Mode)

```
┌─────────────────────────────────────────────────┐
│  [☑ Alle]  3 Pflanzen ausgewählt                │
│                                                 │
│  [💧 Als gegossen markieren] [🌱 Als gedüngt..]│
└─────────────────────────────────────────────────┘
```

- "Alle"-Checkbox toggelt Selektion über **alle aktuell sichtbaren**
  Pflanzen (= nach Raum-Filter)
- Counter zeigt Anzahl ausgewählter Pflanzen (`0` → Action-Buttons disabled)
- Action-Buttons: 💧 Wasser, 🌱 Dünger
- Bei > 5 selected: vor Ausführung Browser-`confirm()` mit Anzahl

### Beenden des Bulk-Modes

- Tap auf "Abbrechen" in der Topbar
- Erfolgreich ausgeführte Bulk-Action: automatisch zurück zu Normal-View
  mit Success-Toast ("8 Pflanzen als gegossen markiert")
- View-Wechsel (Detail / Add / Edit) verlässt Bulk-Mode implizit

## Architektur

Pure Frontend-Änderung in `plant-care-panel.js`. Backend bleibt unverändert.

### State-Modell

```javascript
this._bulkMode = false;          // ist Bulk-Mode aktiv?
this._bulkSelection = new Set(); // Set<plant_id>
```

Beide werden im `_setState`-Trigger berücksichtigt und in `_signature`
mit aufgenommen, damit Re-Renders zuverlässig laufen.

### Render-Pfad

Der `_renderList()` bekommt einen Zweig: wenn `_bulkMode === true`,
wird `_renderCard()` mit einem zusätzlichen Checkbox-Overlay gerendert.
Der Card-Click-Handler verzweigt:

- Bulk-Mode an  → Toggle `_bulkSelection.has(plantId)` (Add/Remove)
- Bulk-Mode aus → "open-detail" wie bisher

Zusätzlich eine neue Render-Methode `_renderBulkActionBar()`, die nur
gerendert wird wenn `_bulkMode === true`. Sie steht im DOM hinter dem
`<main>`-Element der App.

### Action-Dispatch

Bei Klick auf "💧 Als gegossen markieren":

```javascript
async _executeBulkAction(action) {
  const ids = Array.from(this._bulkSelection);
  if (ids.length === 0) return;
  if (ids.length > 5 && !confirm(`${ids.length} Pflanzen als ${actionLabel} markieren?`)) return;

  this._bulkBusy = true;
  this._render();
  try {
    await Promise.all(ids.map(id =>
      this._callService("plant_care", action, { plant_id: id })
    ));
    this._showToast("success", `${ids.length} Pflanzen ${actionPast} markiert`);
    this._bulkSelection.clear();
    this._bulkMode = false;
    this._setState({});
  } catch (err) {
    this._showToast("error", "Bulk-Action fehlgeschlagen: " + this._fmtErr(err));
  } finally {
    this._bulkBusy = false;
    this._render();
  }
}
```

Bei Teilfehler (z.B. 1 von 8 Service-Calls scheitert) wird der ganze
`Promise.all` rejected. Pragmatischer Trade-off: User sieht Fehler-Toast,
die erfolgreich gewässerten Pflanzen sind aber bereits aktualisiert.
Refresh des Panels zeigt den tatsächlichen Stand. Acceptable für v1.

### Style-Pattern

Bulk-Action-Bar bekommt eigene CSS-Klasse `.bulk-bar`:
- `position: sticky; bottom: 0`
- Theme-aware Background (`rgba(126, 174, 110, 0.95)` über `--card-background-color`)
- Box-Shadow nach oben für Tiefe

Checkbox-Overlay auf Cards:
- `position: absolute; top: 8px; left: 8px`
- Mit `pointer-events: none` damit der ganze Card-Click ins Toggle geht
- Visueller Check via CSS-Pseudo-Class

## Edge Cases

| Fall | Verhalten |
|---|---|
| Pflanze während Bulk-Mode anderweitig geändert (z.B. via Mobile-Action) | Re-Render via `_signature` aktualisiert den State; Selection bleibt erhalten (Plant-ID gleich) |
| Pflanze während Bulk-Mode gelöscht | Bulk-Mode-Aktion: Service-Call wirft, Promise.all rejected, Fehler-Toast |
| User wechselt während laufender Bulk-Action das Panel | Bulk-Action läuft im Hintergrund weiter; `_bulkBusy` verhindert Doppelklick |
| Selektion über Raum-Filter-Wechsel hinweg | Selektion bleibt erhalten (Set ist plant_id-basiert), aber unsichtbar wenn Filter ausschließt – "Alle"-Toggle bezieht sich nur auf sichtbare |
| 0 selected → Action-Button | Disabled (CSS + JS-Guard) |

## Tests

Pure-Frontend-Feature, keine neuen Python-Pure-Helper, kein
pytest-relevanter Code. Manueller Test in HA reicht. Falls später
JS-Test-Setup eingeführt wird (out of scope), wäre `_executeBulkAction`
mit Mock-`_callService` testbar.

## Dateien

| Datei | Änderung |
|---|---|
| `custom_components/plant_care/frontend/plant-care-panel.js` | + Bulk-Mode-State, + Toggle-Button, + Render-Pfad, + Action-Bar, + `_executeBulkAction` |
| `README.md` | + kurzer Hinweis im Bedienung-Kapitel |

## Risiken

- **Promise.all Teilerfolg-Problem:** Bei Teil-Fehlschlag bleibt der State
  inkonsistent. Mitigation: User-Hinweis, dass Refresh den realen Stand zeigt.
  Bei häufigem Auftreten könnte man auf `Promise.allSettled` umstellen
  und einen detaillierten Bericht zeigen. Out-of-scope für v1.
- **Lange Bulk-Action ohne Feedback:** 20+ Pflanzen parallel könnte
  spürbar sein. Mitigation: `_bulkBusy`-Flag disabled die Buttons und
  zeigt ⏳. Ausreichend für realistische Pflanzenzahl (< 50).

## Aufwand

Geschätzt 2 h: State+Toggle (~20 min), Checkbox-Overlay-Render (~30 min),
Bottom-Bar + CSS (~30 min), `_executeBulkAction` (~20 min), manueller Test +
README (~20 min).
