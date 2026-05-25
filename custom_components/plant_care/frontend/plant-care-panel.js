/**
 * Plant Care – Sidebar Panel (Vanilla JS Web Component)
 *
 * Views: list | add | edit | detail
 * Datenquelle: hass.states (sensor.plant_* mit attributes.plant_id)
 * Services: plant_care.add_plant / update_plant / remove_plant / water_plant / fertilize_plant
 * KI: ai_task.generate_data (Text + Foto via attachments)
 */

const STATUS_LABEL = {
  ok: "Alles gut",
  needs_water: "Braucht Wasser",
  needs_fertilizer: "Braucht Dünger",
  needs_both: "Wasser + Dünger",
  needs_attention: "🔍 Treatment-Check fällig",
};

const STATUS_CLASS = {
  ok: "ok",
  needs_water: "water",
  needs_fertilizer: "fert",
  needs_both: "both",
  needs_attention: "attention",
};

const ROOM_ALL = "__all__";

const ROOM_LABELS = {
  wohnzimmer: "Wohnzimmer",
  schlafzimmer: "Schlafzimmer",
  kueche: "Küche",
  bad: "Bad",
  buero: "Büro",
  flur: "Flur",
  kinderzimmer: "Kinderzimmer",
};

const LIGHT_LABELS = {
  vollsonne: "Vollsonne (Südfenster)",
  hell: "Hell (am Fenster, nicht direkt)",
  halbschatten: "Halbschatten (1-2m vom Fenster)",
  schatten: "Schatten (weit vom Fenster)",
};

class PlantCarePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._view = "list";
    this._selectedId = null;
    this._draft = null;
    this._toast = null;
    this._toastTimer = null;
    this._roomFilter = ROOM_ALL;
    this._bulkMode = false;
    this._bulkSelection = new Set();
    this._bulkBusy = false;
    this._lightbox = null;
    this._diagnoseModal = null;
    this._calendarEvents = null;
    this._calendarLoading = false;
    this._calendarDays = 14;
    this._aiBusy = false;
    this._listMode = this._loadListMode();
    this._lastStatesSignature = "";
    this._onClick = this._onClick.bind(this);
    this._onSubmit = this._onSubmit.bind(this);
    this._onInput = this._onInput.bind(this);
    this._onChange = this._onChange.bind(this);
  }

  /* ----------------------------- HA-Bindings ----------------------------- */

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  set narrow(v) {
    this._narrow = v;
  }

  set panel(p) {
    this._panel = p;
  }

  set route(r) {
    this._route = r;
  }

  connectedCallback() {
    this._render();
  }

  /* ------------------------------- State --------------------------------- */

  _setState(patch) {
    Object.assign(this, patch);
    this._render(true);
  }

  _loadListMode() {
    try {
      const m = localStorage.getItem("plant_care_list_mode");
      return m === "compact" ? "compact" : "grid";
    } catch {
      return "grid";
    }
  }

  _saveListMode(mode) {
    try {
      localStorage.setItem("plant_care_list_mode", mode);
    } catch {
      // localStorage kann gesperrt sein (Inkognito, etc.) – egal.
    }
  }

  _plants() {
    if (!this._hass) return [];
    return Object.values(this._hass.states)
      .filter((s) => s.attributes && s.attributes.plant_id)
      .map((s) => ({
        entity_id: s.entity_id,
        state: s.state,
        ...s.attributes,
      }));
  }

  _plantById(id) {
    return this._plants().find((p) => p.plant_id === id) || null;
  }

  _signature(plants) {
    return plants
      .map((p) => `${p.plant_id}|${p.state}|${p.last_watered || ""}|${p.last_fertilized || ""}|${p.moisture_pct || ""}|${p.photo ? "p" : ""}`)
      .join("#");
  }

  /* ---------------------------- Auto-Detection --------------------------- */

  _findAiTaskEntity() {
    if (!this._hass) return null;
    const ids = Object.keys(this._hass.states).filter((id) =>
      id.startsWith("ai_task.")
    );
    return ids[0] || null;
  }

  _findMoistureSensors() {
    if (!this._hass) return [];
    return Object.values(this._hass.states)
      .filter((s) => {
        if (!s.entity_id.startsWith("sensor.")) return false;
        const dc = s.attributes && s.attributes.device_class;
        const unit = s.attributes && s.attributes.unit_of_measurement;
        return dc === "moisture" || unit === "%";
      })
      .map((s) => ({
        entity_id: s.entity_id,
        name:
          (s.attributes && s.attributes.friendly_name) || s.entity_id,
      }));
  }

  /* ----------------------------- Service-Calls --------------------------- */

  async _callServiceWithResponse(domain, service, data) {
    // notifyOnError=false: HA soll keinen eigenen Fehler-Toast zeigen,
    // wir formulieren die Meldung selbst.
    let directErr = null;
    try {
      const result = await this._hass.callService(
        domain,
        service,
        data,
        undefined,
        false,
        true,
      );
      if (result && (result.response !== undefined || result.data !== undefined)) {
        return result.response ?? result;
      }
    } catch (err) {
      directErr = err;
      console.warn("[plant_care] callService direct failed, fallback:", err);
    }
    // Pfad 2: execute_script-Fallback (alte HA-Versionen ohne return_response)
    try {
      const result = await this._hass.connection.sendMessagePromise({
        type: "execute_script",
        sequence: [
          {
            service: `${domain}.${service}`,
            data,
            response_variable: "r",
          },
          { stop: "", response_variable: "r" },
        ],
      });
      return result && result.response ? result.response : result;
    } catch (err) {
      console.error("[plant_care] execute_script fallback failed:", err);
      throw directErr || err;
    }
  }

  async _callService(domain, service, data) {
    return this._hass.callService(domain, service, data);
  }

  /* --------------------------------- AI ---------------------------------- */

  _suggestStructure() {
    return {
      species: { selector: { text: {} } },
      common_name: { selector: { text: {} } },
      water_days: { selector: { number: { min: 1, max: 90 } } },
      fertilize_days: { selector: { number: { min: 1, max: 180 } } },
      plant_description: { selector: { text: { multiline: true } } },
    };
  }

  _suggestStructureWithLocation() {
    return {
      ...this._suggestStructure(),
      suitability_warning: { selector: { text: { multiline: true } } },
    };
  }

  _qaContextString(draft) {
    const room = draft.room_type
      ? (ROOM_LABELS[draft.room_type] || draft.room_type)
      : "nicht angegeben";
    const light = draft.light_level
      ? (LIGHT_LABELS[draft.light_level] || draft.light_level)
      : "nicht angegeben";
    return `\n- Standort: ${room}\n- Lichtintensität: ${light}`;
  }

  async _aiSuggestFromName(name) {
    if (!name || !name.trim()) {
      this._showToast("error", "Bitte zuerst einen Namen eingeben");
      return;
    }
    const aiEntity = this._findAiTaskEntity();
    if (!aiEntity) {
      this._showToast("error", "AI Task ist nicht eingerichtet");
      return;
    }
    this._aiBusy = true;
    this._render();
    try {
      const res = await this._callServiceWithResponse(
        "ai_task",
        "generate_data",
        {
          entity_id: aiEntity,
          task_name: "plant_care_suggest",
          instructions:
            `Du bist Botaniker. Für die Zimmerpflanze "${name}":` +
            this._qaContextString(this._draft || {}) +
            `\n\nGib zurück:\n` +
            `- Spezies (botanisch), deutscher Trivialname\n` +
            `- Gieß- und Düngeintervalle in Tagen, passend zum genannten Licht-Level (bei wenig Licht seltener, bei Vollsonne öfter)\n` +
            `- Wenn der genannte Standort für diese Art ungeeignet ist: kurze Begründung im Feld suitability_warning. Sonst leeres Feld.\n` +
            `- Im Feld plant_description (insgesamt 4-6 Sätze): kombiniere Herkunft/Familie/charakteristische Merkmale UND die wichtigsten Pflegehinweise UND was beim genannten Raum + Licht zu beachten ist. Ein zusammenhängender Text, keine Aufzählung.\n` +
            `Antworte ausschließlich im vorgegebenen JSON-Schema.`,
          structure: this._suggestStructureWithLocation(),
        },
      );
      const data = res?.data ?? res?.response?.data ?? res ?? {};
      this._draft = { ...(this._draft || {}), ...data };
      this._showToast("success", "Vorschlag übernommen");
    } catch (err) {
      console.error(err);
      this._showToast("error", "KI-Vorschlag fehlgeschlagen: " + this._fmtErr(err));
    } finally {
      this._aiBusy = false;
      this._render();
    }
  }

  async _aiIdentifyFromPhoto(uploadResult) {
    const aiEntity = this._findAiTaskEntity();
    if (!aiEntity) {
      this._showToast("error", "AI Task ist nicht eingerichtet");
      return;
    }
    this._aiBusy = true;
    this._render();
    try {
      const res = await this._callServiceWithResponse(
        "ai_task",
        "generate_data",
        {
          entity_id: aiEntity,
          task_name: "plant_care_identify_from_photo",
          instructions:
            `Welche Zimmerpflanze ist auf dem angehängten Bild zu sehen?` +
            this._qaContextString(this._draft || {}) +
            `\n\nGib Spezies (botanisch), deutschen Trivialnamen, eine Konfidenz zwischen 0 und 1, ` +
            `empfohlene Gieß- und Düngeintervalle in Tagen passend zum genannten Licht-Level. ` +
            `Im Feld suitability_warning: falls Standort ungeeignet, eine kurze Begründung; sonst leer. ` +
            `Im Feld plant_description (insgesamt 4-6 Sätze): kombiniere Herkunft/Familie/charakteristische Merkmale UND die wichtigsten Pflegehinweise UND was beim genannten Raum + Licht zu beachten ist. Ein zusammenhängender Text, keine Aufzählung. ` +
            `Antworte ausschließlich im vorgegebenen JSON-Schema.`,
          attachments: [
            {
              media_content_id: uploadResult.media_content_id,
              media_content_type: uploadResult.media_content_type || "image/jpeg",
            },
          ],
          structure: {
            ...this._suggestStructureWithLocation(),
            confidence: { selector: { number: { min: 0, max: 1 } } },
          },
        },
      );
      const data = res?.data ?? res?.response?.data ?? res ?? {};
      const conf = typeof data.confidence === "number" ? data.confidence : null;
      this._draft = {
        ...(this._draft || {}),
        ...data,
        photo: uploadResult.path,
      };
      if (!this._draft.name && data.common_name) {
        this._draft.name = data.common_name;
      }
      this._showToast(
        conf !== null && conf < 0.5 ? "info" : "success",
        conf !== null && conf < 0.5
          ? `Erkennung unsicher (${Math.round(conf * 100)}%) – bitte prüfen`
          : "Pflanze erkannt",
      );
    } catch (err) {
      console.error(err);
      this._showToast("error", "Foto-Erkennung fehlgeschlagen: " + this._fmtErr(err));
    } finally {
      this._aiBusy = false;
      this._render();
    }
  }

  /* ---------------------------- Photo Upload ----------------------------- */

  async _resizeImage(file, maxDim = 600, quality = 0.82) {
    const dataUrl = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
    const img = await new Promise((resolve, reject) => {
      const i = new Image();
      i.onload = () => resolve(i);
      i.onerror = reject;
      i.src = dataUrl;
    });
    const scale = Math.min(1, maxDim / Math.max(img.width, img.height));
    const w = Math.round(img.width * scale);
    const h = Math.round(img.height * scale);
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    canvas.getContext("2d").drawImage(img, 0, 0, w, h);
    return canvas.toDataURL("image/jpeg", quality);
  }

  async _uploadPhotoToBackend(dataUrl) {
    // hass.callApi nutzt das vom Frontend verwaltete Token und vermeidet
    // den Griff in interne hass.auth-Strukturen.
    try {
      return await this._hass.callApi("POST", "plant_care/upload", {
        image_base64: dataUrl,
        mime: "image/jpeg",
      });
    } catch (err) {
      const msg =
        err?.body?.message ||
        err?.message ||
        (typeof err === "string" ? err : "Upload fehlgeschlagen");
      throw new Error(msg);
    }
  }

  async _handlePhotoFile(file, opts = {}) {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      this._showToast("error", "Bitte ein Bild auswählen");
      return;
    }
    this._aiBusy = true;
    this._render();
    try {
      const dataUrl = await this._resizeImage(file);
      // Immer hochladen – keine data-URLs im HA-Store, da sonst der
      // plant_care.plants Storage-JSON bei vielen Pflanzen aufgeblasen wird.
      const upload = await this._uploadPhotoToBackend(dataUrl);
      this._draft = { ...(this._draft || {}), photo: upload.path };
      this._render();
      if (opts.identifyWithAi) {
        await this._aiIdentifyFromPhoto(upload);
      }
    } catch (err) {
      console.error(err);
      this._showToast("error", err.message || String(err));
    } finally {
      this._aiBusy = false;
      this._render();
    }
  }

  /* --------------------------------- Toast ------------------------------- */

  _showToast(kind, msg) {
    if (this._toastTimer) clearTimeout(this._toastTimer);
    this._toast = { kind, msg };
    this._render();
    this._toastTimer = setTimeout(() => {
      this._toast = null;
      this._render();
    }, 3000);
  }

  /* ------------------------------ Utilities ------------------------------ */

  _fmtErr(err) {
    if (!err) return "Unbekannter Fehler";
    if (typeof err === "string") return err;
    // HA-WebSocket-Fehler: { code, message }
    const parts = [];
    if (err.message) parts.push(err.message);
    if (err.code && err.code !== err.message) parts.push(`(${err.code})`);
    return parts.length ? parts.join(" ") : String(err);
  }

  _escape(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]),
    );
  }

  _escapeAttr(s) {
    return this._escape(s);
  }

  _relativeTime(iso) {
    if (!iso) return "noch nie";
    const t = Date.parse(iso);
    if (Number.isNaN(t)) return "–";
    const diffMs = Date.now() - t;
    const minutes = Math.floor(diffMs / 60000);
    if (minutes < 1) return "gerade eben";
    if (minutes < 60) return `vor ${minutes} min`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `vor ${hours} h`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `vor ${days} Tag${days === 1 ? "" : "en"}`;
    const months = Math.floor(days / 30);
    return `vor ${months} Monat${months === 1 ? "" : "en"}`;
  }

  /* -------------------------------- Render ------------------------------- */

  _hasFocusedInput() {
    const a = this.shadowRoot && this.shadowRoot.activeElement;
    if (!a || !a.tagName) return false;
    const tag = a.tagName;
    return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
  }

  _render(force = false) {
    if (!this._hass) return;
    // Während ein Formularfeld den Fokus hat, würde innerHTML=...
    // den Input neu rendern und auf Mobile die Tastatur ausblenden.
    // Externe State-Updates (hass-Setter) warten dann auf Blur oder
    // einen erzwungenen Render (force=true).
    if (!force && this._hasFocusedInput()) return;
    const plants = this._plants();
    const sig = [
      this._view,
      this._selectedId || "",
      this._roomFilter,
      this._aiBusy ? 1 : 0,
      this._toast ? this._toast.msg : "",
      this._signature(plants),
      // Volle Draft-Signatur, nicht nur Länge – sonst werden Edits
      // gleicher Länge (z.B. "Monstera" → "Ficus123") nicht re-rendered.
      JSON.stringify(this._draft || {}),
      this._bulkMode ? 1 : 0,
      this._bulkBusy ? 1 : 0,
      Array.from(this._bulkSelection).sort().join(","),
      JSON.stringify(this._lightbox || {}),
      JSON.stringify(this._diagnoseModal || {}),
      this._calendarLoading ? 1 : 0,
      this._calendarDays,
      this._calendarEvents ? this._calendarEvents.length : -1,
    ].join("|");
    if (!force && sig === this._lastStatesSignature) return;
    this._lastStatesSignature = sig;

    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <div class="app">
        <header class="topbar">
          <button class="icon-btn ha-menu" data-action="toggle-ha-menu" aria-label="HA-Seitenleiste umschalten" title="Seitenleiste">☰</button>
          <div class="brand">
            <span class="leaf">🌿</span>
            <h1>Plant Care</h1>
          </div>
          <div class="topbar-spacer"></div>
          ${this._view === "list" ? (this._bulkMode ? `
            <button class="btn ghost" data-action="bulk-cancel">Abbrechen</button>
          ` : `
            <div class="topbar-actions">
              <button class="icon-btn" data-action="show-calendar" aria-label="Kalender" title="Kalender">📅</button>
              <button class="icon-btn" data-action="toggle-list-mode" aria-label="Ansicht wechseln" title="${this._listMode === "compact" ? "Kachel-Ansicht" : "Kompakte Liste"}">${this._listMode === "compact" ? "▦" : "▤"}</button>
              <button class="icon-btn" data-action="bulk-toggle" aria-label="Mehrfachauswahl" title="Auswahl">☑</button>
            </div>
            <button class="btn primary cta" data-action="new">+ Neue Pflanze</button>
          `) : this._view === "calendar" ? `
            <button class="icon-btn" data-action="show-list" aria-label="Listenansicht" title="Liste">📋</button>
            <button class="btn primary cta" data-action="new">+ Neue Pflanze</button>
          ` : `
            <button class="btn ghost" data-action="back">← Zurück</button>
          `}
        </header>
        ${this._toast ? this._renderToast() : ""}
        <main class="main">${this._renderView()}</main>
        ${this._bulkMode && this._view === "list" ? this._renderBulkActionBar() : ""}
        ${this._lightbox ? this._renderLightbox() : ""}
        ${this._diagnoseModal ? this._renderDiagnoseModal() : ""}
      </div>
    `;

    this.shadowRoot.addEventListener("click", this._onClick);
    const form = this.shadowRoot.querySelector("form");
    if (form) {
      form.addEventListener("submit", this._onSubmit);
      form.addEventListener("input", this._onInput);
      form.addEventListener("change", this._onChange);
    }
  }

  _renderToast() {
    const { kind, msg } = this._toast;
    return `<div class="toast ${this._escapeAttr(kind)}">${this._escape(msg)}</div>`;
  }

  _renderView() {
    switch (this._view) {
      case "add":
        return this._renderForm("add");
      case "edit":
        return this._renderForm("edit");
      case "detail":
        return this._renderDetail();
      case "calendar":
        return this._renderAgenda();
      case "list":
      default:
        return this._renderList();
    }
  }

  /* ------------------------------ List View ------------------------------ */

  _renderList() {
    const plants = this._plants();
    if (plants.length === 0) {
      return this._renderEmpty();
    }
    const rooms = Array.from(
      new Set(plants.map((p) => (p.room_type || "").trim()).filter(Boolean)),
    ).sort();
    const hasUnassigned = plants.some((p) => !(p.room_type || "").trim());
    const filter = this._roomFilter;
    const filtered =
      filter === ROOM_ALL
        ? plants
        : filter === ""
          ? plants.filter((p) => !(p.room_type || "").trim())
          : plants.filter((p) => (p.room_type || "").trim() === filter);

    const roomLabel = (r) => ROOM_LABELS[r] || r;
    const roomCount = (r) =>
      plants.filter((p) => (p.room_type || "").trim() === r).length;
    const unassignedCount = plants.filter(
      (p) => !(p.room_type || "").trim(),
    ).length;

    return `
      ${(rooms.length > 0 || hasUnassigned) ? `
        <nav class="rooms">
          <button class="room ${filter === ROOM_ALL ? "active" : ""}" data-action="filter-room" data-room="${ROOM_ALL}">Alle (${plants.length})</button>
          ${rooms.map((r) => `
            <button class="room ${filter === r ? "active" : ""}" data-action="filter-room" data-room="${this._escapeAttr(r)}">
              ${this._escape(roomLabel(r))} (${roomCount(r)})
            </button>
          `).join("")}
          ${hasUnassigned ? `
            <button class="room ${filter === "" ? "active" : ""}" data-action="filter-room" data-room="">
              Ohne Raum (${unassignedCount})
            </button>
          ` : ""}
        </nav>
      ` : ""}
      <div class="${this._listMode === "compact" ? "list-compact" : "grid"}">
        ${filtered.map((p) => this._listMode === "compact" ? this._renderRowCard(p) : this._renderCard(p)).join("")}
      </div>
    `;
  }

  _renderRowCard(p) {
    const status = p.state || "ok";
    const selected = this._bulkMode && this._bulkSelection.has(p.plant_id);
    const cardClass = `row-card${this._bulkMode ? " bulk" : ""}${selected ? " selected" : ""}`;
    const action = this._bulkMode ? "bulk-toggle-card" : "open-detail";
    return `
      <article class="${cardClass}" data-action="${action}" data-id="${this._escapeAttr(p.plant_id)}">
        ${this._bulkMode ? `
          <div class="bulk-check ${selected ? "checked" : ""}" aria-hidden="true">${selected ? "✓" : ""}</div>
        ` : ""}
        <div class="row-photo">
          ${p.photo
            ? `<img src="${this._escapeAttr(p.photo)}" alt="">`
            : `<div class="thumb-placeholder small">🌱</div>`}
        </div>
        <div class="row-info">
          <div class="row-title">${this._escape(p.name)}</div>
          <div class="row-meta">
            <span class="status ${STATUS_CLASS[status] || ""}">${this._escape(STATUS_LABEL[status] || status)}</span>
            <span class="muted small">💧 ${this._escape(this._relativeTime(p.last_watered))}</span>
          </div>
        </div>
        ${this._bulkMode ? "" : `
          <div class="row-actions">
            <button class="card-action-btn" data-action="water" data-id="${this._escapeAttr(p.plant_id)}" aria-label="Gießen" title="Gießen">💧</button>
            <button class="card-action-btn" data-action="fertilize" data-id="${this._escapeAttr(p.plant_id)}" aria-label="Düngen" title="Düngen">🌱</button>
          </div>
        `}
      </article>
    `;
  }

  _renderCard(p) {
    const status = p.state || "ok";
    const selected = this._bulkMode && this._bulkSelection.has(p.plant_id);
    const cardClass = `card${this._bulkMode ? " bulk" : ""}${selected ? " selected" : ""}`;
    const action = this._bulkMode ? "bulk-toggle-card" : "open-detail";
    return `
      <article class="${cardClass}" data-action="${action}" data-id="${this._escapeAttr(p.plant_id)}">
        ${this._bulkMode ? `
          <div class="bulk-check ${selected ? "checked" : ""}" aria-hidden="true">${selected ? "✓" : ""}</div>
        ` : ""}
        <div class="thumb">
          ${p.photo
            ? `<img src="${this._escapeAttr(p.photo)}" alt="">`
            : `<div class="thumb-placeholder">🌱</div>`}
        </div>
        <div class="card-body">
          <h3>${this._escape(p.name)}</h3>
          ${p.species ? `<p class="muted">${this._escape(p.species)}</p>` : ""}
          <div class="card-footer">
            <div class="card-status">
              <p class="status ${STATUS_CLASS[status] || ""}">${this._escape(STATUS_LABEL[status] || status)}</p>
              <p class="muted small">💧 ${this._escape(this._relativeTime(p.last_watered))}</p>
            </div>
            ${this._bulkMode ? "" : `
              <div class="card-actions">
                <button class="card-action-btn" data-action="water" data-id="${this._escapeAttr(p.plant_id)}" aria-label="Gießen" title="Gießen">💧</button>
                <button class="card-action-btn" data-action="fertilize" data-id="${this._escapeAttr(p.plant_id)}" aria-label="Düngen" title="Düngen">🌱</button>
              </div>
            `}
          </div>
        </div>
      </article>
    `;
  }

  _visiblePlants() {
    const plants = this._plants();
    const filter = this._roomFilter;
    if (filter === ROOM_ALL) return plants;
    if (filter === "") {
      return plants.filter((p) => !(p.room_type || "").trim());
    }
    return plants.filter((p) => (p.room_type || "").trim() === filter);
  }

  _renderBulkActionBar() {
    const visiblePlants = this._visiblePlants();
    const visibleIds = visiblePlants.map((p) => p.plant_id);
    const visibleSelectedCount = visibleIds.filter(
      (id) => this._bulkSelection.has(id),
    ).length;
    const allVisibleSelected =
      visibleIds.length > 0 && visibleSelectedCount === visibleIds.length;
    const totalSelected = this._bulkSelection.size;
    const disabled = totalSelected === 0 || this._bulkBusy;
    const busyMark = this._bulkBusy ? " ⏳" : "";
    return `
      <div class="bulk-bar">
        <label class="bulk-bar-select-all">
          <input
            type="checkbox"
            data-action="bulk-select-all"
            ${allVisibleSelected ? "checked" : ""}
            ${this._bulkBusy ? "disabled" : ""}
          />
          <span>Alle</span>
        </label>
        <span class="bulk-bar-count">
          ${totalSelected} ${totalSelected === 1 ? "Pflanze" : "Pflanzen"} ausgewählt
        </span>
        <div class="bulk-bar-actions">
          <button class="btn primary" data-action="bulk-water" ${disabled ? "disabled" : ""}>💧 Gegossen${busyMark}</button>
          <button class="btn primary" data-action="bulk-fertilize" ${disabled ? "disabled" : ""}>🌱 Gedüngt${busyMark}</button>
        </div>
      </div>
    `;
  }

  /* ----------------------------- Agenda View ----------------------------- */

  async _loadCalendar() {
    if (!this._hass) return;
    this._calendarLoading = true;
    this._render();
    try {
      const res = await this._callServiceWithResponse(
        "plant_care",
        "get_events",
        { days: this._calendarDays },
      );
      const events = res?.events ?? res?.response?.events ?? [];
      this._calendarEvents = Array.isArray(events) ? events : [];
    } catch (err) {
      console.error(err);
      this._calendarEvents = [];
      this._showToast(
        "error",
        "Konnte Kalender nicht laden: " + this._fmtErr(err),
      );
    } finally {
      this._calendarLoading = false;
      this._render();
    }
  }

  _renderAgenda() {
    if (this._calendarLoading && this._calendarEvents === null) {
      return `<div class="agenda-loading">⏳ Lade Pflege-Termine…</div>`;
    }
    const events = this._calendarEvents || [];
    if (events.length === 0) {
      return `
        <div class="empty">
          <svg viewBox="0 0 200 200" width="120" height="120" aria-hidden="true">
            <rect x="40" y="50" width="120" height="120" rx="8" fill="none" stroke="#9ec789" stroke-width="3"/>
            <line x1="40" y1="80" x2="160" y2="80" stroke="#9ec789" stroke-width="3"/>
            <circle cx="100" cy="120" r="6" fill="#6b8f5e"/>
          </svg>
          <h2>Keine anstehenden Termine</h2>
          <p class="muted">In den nächsten ${this._calendarDays} Tagen ist nichts fällig.</p>
        </div>
      `;
    }
    const groups = new Map();
    for (const e of events) {
      const key = this._calendarDayKey(e.when);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(e);
    }
    const todayKey = this._calendarDayKey(new Date().toISOString());
    const tomorrowKey = this._calendarDayKey(
      new Date(Date.now() + 86400000).toISOString(),
    );
    const sortedKeys = Array.from(groups.keys()).sort();
    return `
      <section class="agenda">
        ${sortedKeys.map((key) => {
          const dayEvents = groups.get(key);
          const dateLabel = this._formatAgendaDay(key, todayKey, tomorrowKey);
          const isToday = key === todayKey;
          return `
            <div class="agenda-day ${isToday ? "today" : ""}">
              <h3 class="agenda-day-label">${this._escape(dateLabel)}</h3>
              <ul class="agenda-events">
                ${dayEvents.map((e) => this._renderAgendaEvent(e, isToday)).join("")}
              </ul>
            </div>
          `;
        }).join("")}
        <div class="agenda-footer">
          <button class="btn ghost" data-action="calendar-more">
            Mehr anzeigen (+14 Tage)
          </button>
        </div>
      </section>
    `;
  }

  _renderAgendaEvent(e, isTodaySection) {
    const icon = e.kind === "water" ? "💧" : "🌱";
    const label = e.kind === "water" ? "gießen" : "düngen";
    const service = e.kind === "water" ? "water" : "fertilize";
    const overdueLabel = e.overdue
      ? `<span class="agenda-overdue">⚠ überfällig</span>`
      : "";
    const showActionButton = isTodaySection || e.overdue;
    const plant = this._plantById(e.plant_id);
    const photo = plant && plant.photo ? plant.photo : "";
    return `
      <li class="agenda-event ${e.overdue ? "overdue" : ""}">
        <button class="agenda-event-main" data-action="open-detail" data-id="${this._escapeAttr(e.plant_id)}">
          <span class="agenda-photo">
            ${photo
              ? `<img src="${this._escapeAttr(photo)}" alt="">`
              : `<span class="thumb-placeholder small">🌱</span>`}
            <span class="agenda-photo-badge">${icon}</span>
          </span>
          <span class="agenda-event-info">
            <span class="agenda-event-name">${this._escape(e.name)}</span>
            <span class="agenda-event-action muted small">${label}${overdueLabel ? "" : ""}</span>
          </span>
          ${overdueLabel}
        </button>
        ${showActionButton ? `
          <button class="btn primary small agenda-action-btn" data-action="${service}" data-id="${this._escapeAttr(e.plant_id)}" title="Als erledigt markieren">✓</button>
        ` : ""}
      </li>
    `;
  }

  _calendarDayKey(isoString) {
    const date = new Date(isoString);
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  }

  _formatAgendaDay(key, todayKey, tomorrowKey) {
    const date = new Date(key + "T00:00:00");
    const formatted = date.toLocaleDateString("de-DE", {
      weekday: "long",
      day: "2-digit",
      month: "long",
    });
    if (key === todayKey) return `HEUTE · ${formatted}`;
    if (key === tomorrowKey) return `MORGEN · ${formatted}`;
    return formatted;
  }

  _renderEmpty() {
    return `
      <div class="empty">
        <svg viewBox="0 0 200 200" width="160" height="160" aria-hidden="true">
          <ellipse cx="100" cy="170" rx="60" ry="10" fill="rgba(0,0,0,0.08)"/>
          <path d="M100 170 L100 100" stroke="#6b8f5e" stroke-width="3" fill="none"/>
          <path d="M100 130 Q70 110 60 80 Q90 100 100 130 Z" fill="#7fae6e"/>
          <path d="M100 110 Q130 90 140 60 Q110 80 100 110 Z" fill="#9ec789"/>
          <path d="M100 90 Q80 70 75 40 Q100 60 100 90 Z" fill="#6b8f5e"/>
        </svg>
        <h2>Noch keine Pflanzen</h2>
        <p class="muted">Lege deine erste Pflanze an und lass dich von der KI bei der Pflege unterstützen.</p>
        <button class="btn primary" data-action="new">+ Neue Pflanze</button>
      </div>
    `;
  }

  /* ------------------------------ Form View ------------------------------ */

  _renderForm(mode) {
    const draft = this._draft || {};
    const aiAvailable = !!this._findAiTaskEntity();
    const sensors = this._findMoistureSensors();

    return `
      <h2 class="page-title">${mode === "edit" ? "Pflanze bearbeiten" : "Neue Pflanze"}</h2>

      <form>
        <section class="form-section">
          <header class="form-section-head">
            <span class="form-section-label">Identifikation</span>
          </header>
          <label class="field">
            <span>Name *</span>
            <input name="name" value="${this._escapeAttr(draft.name || "")}" required autocomplete="off">
          </label>
          <div class="ai-actions">
            <button type="button" class="btn ${aiAvailable ? "" : "disabled"}" data-action="ai-suggest" ${!aiAvailable ? "disabled" : ""} title="${aiAvailable ? "" : "AI Task nicht eingerichtet"}">
              ${this._aiBusy ? "⏳ …" : "✨ KI-Vorschlag"}
            </button>
            ${aiAvailable ? `
              <button type="button" class="btn" data-action="photo-identify" ${this._aiBusy ? "disabled" : ""}>
                📷 Per Foto erkennen
              </button>
              <input type="file" accept="image/*" id="photo-identify-input" style="display:none">
            ` : ""}
          </div>
        </section>

        <section class="form-section">
          <header class="form-section-head">
            <span class="form-section-label">📍 Standort</span>
            <span class="form-section-hint">optional</span>
          </header>
          ${this._renderLocationLightFields(draft)}
          <label class="field">
            <span>Position (Detail)</span>
            <input name="location" value="${this._escapeAttr(draft.location || "")}" autocomplete="off" placeholder="z.B. Fensterbank Nord">
          </label>
          ${draft.suitability_warning ? `
            <div class="location-tips-card">
              <div class="warning-banner inline">
                <strong>⚠ Achtung</strong>
                <p>${this._escape(draft.suitability_warning)}</p>
              </div>
            </div>
          ` : ""}
        </section>

        <section class="form-section">
          <header class="form-section-head">
            <span class="form-section-label">💧 Pflege-Intervalle</span>
          </header>
          <div class="form-grid form-grid-3">
            <label class="field">
              <span>Gießen (Tage)</span>
              <input name="water_days" type="number" min="1" max="90" value="${this._escapeAttr(draft.water_days || 7)}">
            </label>
            <label class="field">
              <span>Düngen (Tage)</span>
              <input name="fertilize_days" type="number" min="1" max="180" value="${this._escapeAttr(draft.fertilize_days || 30)}">
            </label>
            <label class="field">
              <span>Bodenfeuchte-Sensor</span>
              <select name="moisture_sensor">
                <option value="">– kein Sensor –</option>
                ${sensors.map((s) => `
                  <option value="${this._escapeAttr(s.entity_id)}" ${draft.moisture_sensor === s.entity_id ? "selected" : ""}>
                    ${this._escape(s.name)}
                  </option>
                `).join("")}
              </select>
            </label>
          </div>
        </section>

        <section class="form-section">
          <header class="form-section-head">
            <span class="form-section-label">🌿 Pflanzen-Info</span>
          </header>
          <div class="form-grid form-grid-2">
            <label class="field">
              <span>Spezies</span>
              <input name="species" value="${this._escapeAttr(draft.species || "")}" autocomplete="off" placeholder="z.B. Monstera deliciosa">
            </label>
            <label class="field">
              <span>Trivialname</span>
              <input name="common_name" value="${this._escapeAttr(draft.common_name || "")}" autocomplete="off" placeholder="z.B. Fensterblatt">
            </label>
          </div>
          <label class="field">
            <span>Foto</span>
            <input type="file" name="photo_file" accept="image/*">
            ${draft.photo ? `
              <div class="photo-preview">
                <img src="${this._escapeAttr(draft.photo)}" alt="">
                <button type="button" class="btn ghost small" data-action="clear-photo">Foto entfernen</button>
              </div>
            ` : ""}
          </label>
          <label class="field">
            <span>Über diese Pflanze</span>
            <textarea name="plant_description" rows="6" placeholder="Von KI gefüllt oder selbst notiert. 4-6 Sätze: Herkunft + Pflege + Standort-Hinweise in einem zusammenhängenden Text.">${this._escape(draft.plant_description || "")}</textarea>
          </label>
        </section>

        <div class="actions">
          <button type="submit" class="btn primary">Speichern</button>
          <button type="button" class="btn ghost" data-action="cancel">Abbrechen</button>
          ${mode === "edit" ? `
            <button type="button" class="btn danger" data-action="delete">Löschen</button>
          ` : ""}
        </div>
      </form>
    `;
  }

  _renderLocationLightFields(draft) {
    const roomValue = draft.room_type || "";
    const roomIsStandard = !roomValue || Object.prototype.hasOwnProperty.call(ROOM_LABELS, roomValue);
    const roomSelectValue = roomIsStandard ? roomValue : "__other__";
    const lightValue = draft.light_level || "";
    return `
      <div class="form-grid form-grid-2 location-grid">
        <label class="field">
          <span>Raum</span>
          <select name="room_type_select" data-action="set-room">
            <option value="">– nicht angegeben –</option>
            ${Object.entries(ROOM_LABELS).map(([val, label]) => `
              <option value="${this._escapeAttr(val)}" ${roomSelectValue === val ? "selected" : ""}>${this._escape(label)}</option>
            `).join("")}
            <option value="__other__" ${roomSelectValue === "__other__" ? "selected" : ""}>Andere…</option>
          </select>
          ${roomSelectValue === "__other__" ? `
            <input name="room_type_other" type="text" placeholder="Raum-Bezeichnung" value="${this._escapeAttr(roomValue)}" autocomplete="off">
          ` : ""}
        </label>

        <div class="field">
          <span class="field-label">Lichtintensität</span>
          <div class="radio-group">
            <label class="radio-pill"><input type="radio" name="light_level" value=""             ${lightValue === ""             ? "checked" : ""}><span>Weiß nicht</span></label>
            <label class="radio-pill"><input type="radio" name="light_level" value="vollsonne"    ${lightValue === "vollsonne"    ? "checked" : ""}><span>${this._escape(LIGHT_LABELS.vollsonne)}</span></label>
            <label class="radio-pill"><input type="radio" name="light_level" value="hell"         ${lightValue === "hell"         ? "checked" : ""}><span>${this._escape(LIGHT_LABELS.hell)}</span></label>
            <label class="radio-pill"><input type="radio" name="light_level" value="halbschatten" ${lightValue === "halbschatten" ? "checked" : ""}><span>${this._escape(LIGHT_LABELS.halbschatten)}</span></label>
            <label class="radio-pill"><input type="radio" name="light_level" value="schatten"     ${lightValue === "schatten"     ? "checked" : ""}><span>${this._escape(LIGHT_LABELS.schatten)}</span></label>
          </div>
        </div>
      </div>
    `;
  }

  /* ----------------------------- Detail View ----------------------------- */

  _renderDetail() {
    const p = this._plantById(this._selectedId);
    if (!p) {
      return `<p class="muted">Pflanze nicht gefunden.</p>`;
    }
    const status = p.state || "ok";
    const moisture = p.moisture_pct;
    const moistureValue =
      typeof moisture === "number" ? Math.max(0, Math.min(100, moisture)) : null;

    return `
      <article class="detail">
        ${this._renderSuitabilityWarning(p)}
        <header class="detail-header">
          <div class="detail-photo">
            ${p.photo
              ? `<img src="${this._escapeAttr(p.photo)}" alt="">`
              : `<div class="thumb-placeholder large">🌱</div>`}
          </div>
          <div class="detail-meta">
            <h2>${this._escape(p.name)}</h2>
            ${p.species ? `<p class="species muted">${this._escape(p.species)}</p>` : ""}
            ${(p.room_type || p.light_level || p.location) ? `
              <p class="facts muted">
                ${p.room_type ? `<span>🏠 ${this._escape(ROOM_LABELS[p.room_type] || p.room_type)}</span>` : ""}
                ${p.light_level ? `<span>💡 ${this._escape(LIGHT_LABELS[p.light_level] || p.light_level)}</span>` : ""}
                ${p.location ? `<span>📍 ${this._escape(p.location)}</span>` : ""}
              </p>
            ` : ""}
            <div class="meta-row">
              <span class="status ${STATUS_CLASS[status] || ""}">${this._escape(STATUS_LABEL[status] || status)}</span>
              <button class="btn ghost small" data-action="edit" data-id="${this._escapeAttr(p.plant_id)}">Bearbeiten</button>
            </div>
          </div>
        </header>

        <div class="quick-actions">
          <button class="btn primary quick-action" data-action="water" data-id="${this._escapeAttr(p.plant_id)}" title="Intervall: alle ${this._escape(p.water_days)} Tage">
            <span class="qa-icon">💧</span>
            <span class="qa-label">Gießen</span>
            <span class="qa-meta">${this._escape(this._relativeTime(p.last_watered))}</span>
          </button>
          <button class="btn primary quick-action" data-action="fertilize" data-id="${this._escapeAttr(p.plant_id)}" title="Intervall: alle ${this._escape(p.fertilize_days)} Tage">
            <span class="qa-icon">🌱</span>
            <span class="qa-label">Düngen</span>
            <span class="qa-meta">${this._escape(this._relativeTime(p.last_fertilized))}</span>
          </button>
        </div>

        ${this._renderAboutSection(p)}

        ${moistureValue !== null ? `
          <section class="moisture-section">
            <h3>📊 Bodenfeuchte</h3>
            <div class="moisture-bar">
              <div class="moisture-fill" style="width:${moistureValue}%"></div>
              <span class="moisture-label">${Math.round(moistureValue)}%</span>
            </div>
            <p class="muted small">${this._escape(p.moisture_sensor)}</p>
          </section>
        ` : ""}

        ${this._renderTreatments(p)}

        ${this._renderPhotoHistory(p)}

        ${this._renderHistorySection(p)}
      </article>
    `;
  }

  _renderAboutSection(p) {
    // Legacy-Konsolidierung: falls noch separates tips/location_tips
    // existiert (vor Migration auf plant_description), in einen Text mergen.
    const desc = (p.plant_description || "").trim();
    const tips = (p.tips || "").trim();
    const legacy = (p.location_tips || "").trim();
    const parts = [desc];
    if (tips && !desc.includes(tips)) parts.push(tips);
    if (legacy && !desc.includes(legacy) && !tips.includes(legacy)) parts.push(legacy);
    const combined = parts.filter(Boolean).join("\n\n");
    if (!combined) return "";
    return `
      <section class="about-section">
        <h3>🌿 Über diese Pflanze</h3>
        <p>${this._escape(combined)}</p>
      </section>
    `;
  }

  _renderTreatments(p) {
    const treatments = Array.isArray(p.treatments) ? p.treatments : [];
    const open = treatments.filter((t) => t.status === "open");
    const closed = treatments.filter((t) => t.status !== "open");
    return `
      <section class="treatments">
        <h3>🔍 Behandlungen</h3>
        <div class="treatment-actions">
          <button class="btn" data-action="open-diagnose" data-id="${this._escapeAttr(p.plant_id)}">
            + Was ist los?
          </button>
        </div>
        ${open.length === 0 && closed.length === 0 ? `
          <p class="muted small">Noch keine Behandlungen dokumentiert.</p>
        ` : ""}
        ${open.map((t) => this._renderTreatmentCard(p.plant_id, t, false)).join("")}
        ${closed.length > 0 ? `
          <details class="closed-treatments">
            <summary class="muted small">${closed.length} abgeschlossene Behandlung${closed.length === 1 ? "" : "en"}</summary>
            ${closed.map((t) => this._renderTreatmentCard(p.plant_id, t, true)).join("")}
          </details>
        ` : ""}
      </section>
    `;
  }

  _renderTreatmentCard(plantId, t, closed) {
    const dateStr = t.started_at ? this._relativeTime(t.started_at) : "";
    const dueStr = t.follow_up_at && !closed ? this._relativeTime(t.follow_up_at) : "";
    const confidence = typeof t.confidence === "number" ? Math.round(t.confidence * 100) : null;
    return `
      <article class="treatment-card ${closed ? "closed" : "open"}">
        <header>
          <span class="treatment-icon">${closed ? (t.status === "resolved" ? "✓" : "✗") : "⚠"}</span>
          <strong>${this._escape(t.diagnosis || "")}</strong>
          ${confidence !== null ? `<span class="muted small">(${confidence}% sicher)</span>` : ""}
        </header>
        <p class="muted small">Begonnen: ${this._escape(dateStr)}${dueStr ? ` · Fällig: ${this._escape(dueStr)}` : ""}</p>
        ${Array.isArray(t.treatment_steps) && t.treatment_steps.length > 0 ? `
          <ol class="treatment-steps">
            ${t.treatment_steps.map((s) => `<li>${this._escape(s)}</li>`).join("")}
          </ol>
        ` : ""}
        ${!closed ? `
          <div class="treatment-actions-row">
            <button class="btn primary small" data-action="resolve-treatment" data-id="${this._escapeAttr(plantId)}" data-treatment="${this._escapeAttr(t.id)}">✓ Erledigt</button>
            <button class="btn ghost small" data-action="dismiss-treatment" data-id="${this._escapeAttr(plantId)}" data-treatment="${this._escapeAttr(t.id)}">✗ Verwerfen</button>
          </div>
        ` : ""}
      </article>
    `;
  }

  _renderDiagnoseModal() {
    if (!this._diagnoseModal) return "";
    const { plantId, busy, result, error, mode, manualDraft } = this._diagnoseModal;
    const plant = this._plantById(plantId);
    if (!plant) return "";
    const aiAvailable = !!this._findAiTaskEntity();
    return `
      <div class="lightbox" data-action="close-diagnose">
        <div class="lightbox-content" data-stop style="max-width:560px">
          <header class="lightbox-header">
            <h3>Diagnose: ${this._escape(plant.name)}</h3>
          </header>
          <div class="diagnose-body">
            ${this._renderDiagnoseBody(plantId, { busy, result, error, mode, manualDraft, aiAvailable })}
          </div>
          <footer class="lightbox-footer">
            ${result && result.shouldSave ? `
              <button class="btn primary" data-action="save-diagnose" data-id="${this._escapeAttr(plantId)}">✓ Speichern</button>
            ` : ""}
            ${mode === "manual" && !busy ? `
              <button class="btn primary" data-action="save-manual-diagnose" data-id="${this._escapeAttr(plantId)}">✓ Speichern</button>
            ` : ""}
            <button class="btn ghost" data-action="close-diagnose-btn">Schließen</button>
          </footer>
        </div>
      </div>
    `;
  }

  _renderDiagnoseBody(plantId, { busy, result, error, mode, manualDraft, aiAvailable }) {
    if (result) return this._renderDiagnoseResult(this._plantById(plantId), result);
    if (busy) return `<p>⏳ Foto wird analysiert…</p>`;
    if (error) return `<p class="error">${this._escape(error)}</p>`;
    if (mode === "manual") return this._renderManualDiagnoseForm(plantId, manualDraft || {});
    // Initial: Mode-Auswahl
    return `
      <p class="muted">Wähle eine Methode:</p>
      <div class="diagnose-mode-choice">
        ${aiAvailable ? `
          <button class="btn primary" data-action="pick-diagnose-photo" data-id="${this._escapeAttr(plantId)}">
            📷 Foto-Diagnose
            <small>KI analysiert ein Bild</small>
          </button>
          <input type="file" accept="image/*" id="diagnose-photo-input" style="display:none">
        ` : ""}
        <button class="btn ${aiAvailable ? "ghost" : "primary"}" data-action="start-manual-diagnose" data-id="${this._escapeAttr(plantId)}">
          ✏️ Selbst beschreiben
          <small>Manuell ohne KI</small>
        </button>
      </div>
      ${!aiAvailable ? `<p class="muted small">AI Task ist nicht eingerichtet – Foto-Diagnose nicht verfügbar.</p>` : ""}
    `;
  }

  _renderManualDiagnoseForm(plantId, draft) {
    return `
      <form class="manual-diagnose" data-stop>
        <label class="field">
          <span>Was ist los? *</span>
          <textarea name="diagnosis" rows="2" placeholder="z.B. Spinnmilben an den Blättern, gelbe Flecken" required>${this._escape(draft.diagnosis || "")}</textarea>
        </label>
        <label class="field">
          <span>Geplante Schritte (eine pro Zeile)</span>
          <textarea name="treatment_steps" rows="3" placeholder="Blätter mit Seifenlösung abwischen&#10;Luftfeuchtigkeit erhöhen">${this._escape(draft.treatment_steps_text || "")}</textarea>
        </label>
        <div class="form-grid form-grid-2">
          <label class="field">
            <span>Wiedervorlage (Tage)</span>
            <input type="number" name="follow_up_days" min="1" max="30" value="${this._escapeAttr(draft.follow_up_days || 7)}">
          </label>
          <label class="field">
            <span>Schweregrad</span>
            <select name="severity">
              <option value="low" ${draft.severity === "low" ? "selected" : ""}>Niedrig</option>
              <option value="medium" ${(draft.severity || "medium") === "medium" ? "selected" : ""}>Mittel</option>
              <option value="high" ${draft.severity === "high" ? "selected" : ""}>Hoch</option>
            </select>
          </label>
        </div>
      </form>
    `;
  }

  _renderDiagnoseResult(plant, result) {
    const conf = typeof result.confidence === "number" ? Math.round(result.confidence * 100) : null;
    const healthy = (result.confidence ?? 1) < 0.5 || /keine auffäl/i.test(result.diagnosis || "");
    if (healthy) {
      return `<p style="font-size:1.1rem;color:var(--sage)">✓ Sieht gesund aus!</p>
              <p class="muted">${this._escape(result.diagnosis || "")}</p>`;
    }
    const steps = Array.isArray(result.treatment_steps) ? result.treatment_steps : [];
    return `
      <strong>${this._escape(result.diagnosis || "Diagnose")}</strong>
      ${conf !== null ? `<p class="muted small">Konfidenz: ${conf}%</p>` : ""}
      ${steps.length ? `
        <p style="margin-top:12px"><strong>Empfohlene Schritte:</strong></p>
        <ol>${steps.map((s) => `<li>${this._escape(s)}</li>`).join("")}</ol>
      ` : ""}
      <p class="muted small">Wiedervorlage in ${result.follow_up_days || 7} Tagen.</p>
    `;
  }

  async _runDiagnose(plantId, file) {
    if (!file || !file.type.startsWith("image/")) {
      this._showToast("error", "Bitte ein Bild auswählen");
      return;
    }
    const aiEntity = this._findAiTaskEntity();
    if (!aiEntity) {
      this._showToast("error", "AI Task nicht eingerichtet");
      return;
    }
    this._diagnoseModal = { plantId, busy: true };
    this._render();
    try {
      const dataUrl = await this._resizeImage(file);
      const upload = await this._uploadPhotoToBackend(dataUrl);
      const res = await this._callServiceWithResponse(
        "ai_task", "generate_data",
        {
          entity_id: aiEntity,
          task_name: "plant_care_diagnose",
          instructions:
            "Du bist erfahrener Botaniker und Pflanzenarzt. Auf dem angehängten Foto " +
            "ist eine Pflanze. Analysiere mögliche Schädlinge, Krankheiten oder " +
            "Pflegefehler. Wenn die Pflanze gesund aussieht: diagnosis='Keine " +
            "Auffälligkeiten erkannt', confidence < 0.5. Antworte ausschließlich " +
            "im vorgegebenen JSON-Schema.",
          attachments: [
            {
              media_content_id: upload.media_content_id,
              media_content_type: upload.media_content_type || "image/jpeg",
            },
          ],
          structure: {
            diagnosis: { selector: { text: { multiline: true } } },
            confidence: { selector: { number: { min: 0, max: 1 } } },
            treatment_steps: { selector: { object: {} } },
            follow_up_days: { selector: { number: { min: 1, max: 30 } } },
            severity: { selector: { select: { options: ["low", "medium", "high"] } } },
          },
        },
      );
      const data = res?.data ?? res?.response?.data ?? res ?? {};
      const healthy = (data.confidence ?? 1) < 0.5 ||
        /keine auffäl/i.test(data.diagnosis || "");
      this._diagnoseModal = {
        plantId,
        busy: false,
        result: { ...data, shouldSave: !healthy, photo_path: upload.path },
      };
    } catch (err) {
      console.error(err);
      this._diagnoseModal = { plantId, busy: false, error: this._fmtErr(err) };
    } finally {
      this._render();
    }
  }

  async _saveManualDiagnose(plantId) {
    const form = this.shadowRoot.querySelector(".manual-diagnose");
    if (!form) return;
    const fd = new FormData(form);
    const diagnosis = (fd.get("diagnosis") || "").toString().trim();
    if (!diagnosis) {
      this._showToast("error", "Bitte eine Beschreibung eingeben");
      return;
    }
    const stepsText = (fd.get("treatment_steps") || "").toString();
    const steps = stepsText
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    const followUp = parseInt(fd.get("follow_up_days") || "7", 10);
    const severity = (fd.get("severity") || "medium").toString();
    try {
      await this._callServiceWithResponse("plant_care", "diagnose_plant", {
        plant_id: plantId,
        photo_path: "",
        ai_response: {
          diagnosis,
          treatment_steps: steps,
          follow_up_days: isNaN(followUp) ? 7 : followUp,
          severity,
        },
      });
      this._showToast("success", "Behandlung dokumentiert");
      this._diagnoseModal = null;
      this._setState({});
    } catch (err) {
      this._showToast("error", this._fmtErr(err));
    }
  }

  async _saveDiagnose(plantId) {
    const modal = this._diagnoseModal;
    if (!modal?.result?.shouldSave) return;
    try {
      await this._callServiceWithResponse("plant_care", "diagnose_plant", {
        plant_id: plantId,
        photo_path: modal.result.photo_path,
        ai_response: {
          diagnosis: modal.result.diagnosis,
          confidence: modal.result.confidence,
          treatment_steps: modal.result.treatment_steps,
          follow_up_days: modal.result.follow_up_days,
          severity: modal.result.severity,
        },
      });
      this._showToast("success", "Behandlung dokumentiert");
      this._diagnoseModal = null;
      this._setState({});
    } catch (err) {
      this._showToast("error", this._fmtErr(err));
    }
  }

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

  _renderLightbox() {
    if (!this._lightbox) return "";
    const plant = this._plantById(this._lightbox.plantId);
    if (!plant) return "";
    const photos = Array.isArray(plant.photos) ? plant.photos : [];
    if (photos.length === 0) return "";
    const idx = Math.max(0, Math.min(this._lightbox.idx, photos.length - 1));
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
            <button class="btn small" data-action="lightbox-close-btn">Schließen</button>
          </footer>
        </div>
      </div>
    `;
  }

  _renderSuitabilityWarning(p) {
    if (!p.suitability_warning) return "";
    return `
      <div class="warning-banner detail-warning">
        <button class="warning-dismiss" data-action="dismiss-warning" data-id="${this._escapeAttr(p.plant_id)}" aria-label="Warnung ausblenden">✕</button>
        <strong>⚠ Achtung</strong>
        <p>${this._escape(p.suitability_warning)}</p>
      </div>
    `;
  }

  _renderHistorySection(p) {
    const water = p.water_history || [];
    const fert = p.fertilize_history || [];
    if (water.length === 0 && fert.length === 0) {
      return "";
    }
    return `
      <section class="history">
        <h3>Verlauf (90 Tage)</h3>
        <div class="chart-row">
          <div class="chart-label">💧 Gießen (${water.length})</div>
          ${this._renderChart(water)}
        </div>
        <div class="chart-row">
          <div class="chart-label">🌱 Düngen (${fert.length})</div>
          ${this._renderChart(fert)}
        </div>
      </section>
    `;
  }

  _renderChart(history) {
    const W = 320;
    const H = 50;
    const P = 8;
    const now = Date.now();
    // Muss zu HISTORY_MAX_ENTRIES in const.py passen, sonst zeigt der
    // Chart bei sehr häufigen Events einen abgeschnittenen Zeitraum.
    const daySpan = 90;
    const spanMs = daySpan * 86400000;
    const points = (history || [])
      .map((iso) => Date.parse(iso))
      .filter((t) => !Number.isNaN(t) && now - t < spanMs)
      .map((t) => {
        const x = P + (W - 2 * P) * (1 - (now - t) / spanMs);
        return `<circle cx="${x.toFixed(1)}" cy="${H / 2}" r="3" fill="var(--primary-color, #6b8f5e)"/>`;
      })
      .join("");
    const baseline = `<line x1="${P}" y1="${H / 2}" x2="${W - P}" y2="${H / 2}" stroke="var(--divider-color, #d0d0d0)" stroke-dasharray="2 3"/>`;
    return `
      <svg viewBox="0 0 ${W} ${H}" class="chart" preserveAspectRatio="none">
        ${baseline}
        ${points}
      </svg>
      <div class="chart-axis"><span>vor ${daySpan} Tagen</span><span>heute</span></div>
    `;
  }

  /* ------------------------------- Events -------------------------------- */

  _onClick(evt) {
    const target = evt.target.closest("[data-action]");
    if (!target) return;
    const action = target.dataset.action;
    const id = target.dataset.id;

    switch (action) {
      case "show-calendar":
        this._view = "calendar";
        this._setState({});
        this._loadCalendar();
        break;
      case "show-list":
        this._view = "list";
        this._setState({});
        break;
      case "toggle-list-mode":
        this._listMode = this._listMode === "compact" ? "grid" : "compact";
        this._saveListMode(this._listMode);
        this._setState({});
        break;
      case "toggle-ha-menu":
        // HA-Standard-Event – wird von HA-Main aufgefangen und togglet
        // die Seitenleiste. Muss aus dem Shadow Root heraus bubbeln.
        this.dispatchEvent(
          new Event("hass-toggle-menu", { bubbles: true, composed: true }),
        );
        break;
      case "calendar-more":
        this._calendarDays = Math.min(180, this._calendarDays + 14);
        this._loadCalendar();
        break;
      case "bulk-toggle":
        this._bulkMode = true;
        this._bulkSelection = new Set();
        this._setState({});
        break;
      case "bulk-cancel":
        this._bulkMode = false;
        this._bulkSelection = new Set();
        this._setState({});
        break;
      case "bulk-toggle-card":
        if (!this._bulkMode) break;
        if (this._bulkSelection.has(id)) {
          this._bulkSelection.delete(id);
        } else {
          this._bulkSelection.add(id);
        }
        this._setState({});
        break;
      case "bulk-select-all": {
        const visible = this._visiblePlants();
        const visibleIds = visible.map((p) => p.plant_id);
        const allSelected =
          visibleIds.length > 0 &&
          visibleIds.every((idv) => this._bulkSelection.has(idv));
        if (allSelected) {
          visibleIds.forEach((idv) => this._bulkSelection.delete(idv));
        } else {
          visibleIds.forEach((idv) => this._bulkSelection.add(idv));
        }
        this._setState({});
        break;
      }
      case "open-diagnose":
        this._diagnoseModal = { plantId: id, busy: false, mode: "choose" };
        this._setState({});
        break;
      case "start-manual-diagnose":
        this._diagnoseModal = {
          plantId: id,
          busy: false,
          mode: "manual",
          manualDraft: { follow_up_days: 7, severity: "medium" },
        };
        this._setState({});
        break;
      case "save-manual-diagnose":
        this._saveManualDiagnose(id);
        break;
      case "close-diagnose":
        // Click auf Backdrop schließt; Click im Content nicht.
        if (evt.target.closest("[data-stop]")) break;
        if (this._diagnoseModal?.busy) break;
        this._diagnoseModal = null;
        this._setState({});
        break;
      case "close-diagnose-btn":
        if (this._diagnoseModal?.busy) break;
        this._diagnoseModal = null;
        this._setState({});
        break;
      case "pick-diagnose-photo": {
        const input = this.shadowRoot.getElementById("diagnose-photo-input");
        if (input) {
          input.onchange = (e) => {
            const file = e.target.files && e.target.files[0];
            if (file) this._runDiagnose(id, file);
          };
          input.click();
        }
        break;
      }
      case "save-diagnose":
        this._saveDiagnose(id);
        break;
      case "resolve-treatment":
        this._callService("plant_care", "resolve_treatment", {
          plant_id: id,
          treatment_id: target.dataset.treatment,
          outcome: "resolved",
        }).then(() => this._showToast("success", "Behandlung erledigt"))
          .catch((err) => this._showToast("error", this._fmtErr(err)));
        break;
      case "dismiss-treatment":
        this._callService("plant_care", "resolve_treatment", {
          plant_id: id,
          treatment_id: target.dataset.treatment,
          outcome: "dismissed",
        }).then(() => this._showToast("success", "Behandlung verworfen"))
          .catch((err) => this._showToast("error", this._fmtErr(err)));
        break;
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
      case "open-lightbox":
        this._lightbox = { plantId: id, idx: parseInt(target.dataset.idx, 10) || 0 };
        this._setState({});
        break;
      case "lightbox-close":
        // Click on backdrop schließt; Click im Content nicht (data-stop).
        if (evt.target.closest("[data-stop]")) break;
        this._lightbox = null;
        this._setState({});
        break;
      case "lightbox-close-btn":
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
      case "dismiss-warning":
        this._callService("plant_care", "update_plant", {
          plant_id: id,
          suitability_warning: "",
        })
          .then(() => this._showToast("success", "Warnung ausgeblendet"))
          .catch((err) => this._showToast("error", this._fmtErr(err)));
        break;
      case "bulk-water":
        this._executeBulkAction("water_plant");
        break;
      case "bulk-fertilize":
        this._executeBulkAction("fertilize_plant");
        break;
      case "new":
        this._draft = {};
        this._setState({ _view: "add" });
        break;
      case "back":
      case "cancel":
        this._draft = null;
        this._setState({ _view: "list", _selectedId: null });
        break;
      case "open-detail":
        this._setState({ _view: "detail", _selectedId: id });
        break;
      case "edit": {
        const p = this._plantById(id);
        if (p) {
          // Alle persistierten Felder in den Draft kopieren, damit das
          // Edit-Form keine Werte verliert.
          // Legacy: tips + location_tips in plant_description mergen,
          // falls Storage-Migration noch nicht lief.
          const baseDesc = (p.plant_description || "").trim();
          const legacyTips = (p.tips || "").trim();
          const legacyLoc = (p.location_tips || "").trim();
          const parts = [baseDesc];
          if (legacyTips && !baseDesc.includes(legacyTips)) parts.push(legacyTips);
          if (legacyLoc && !baseDesc.includes(legacyLoc) && !legacyTips.includes(legacyLoc)) parts.push(legacyLoc);
          const mergedDesc = parts.filter(Boolean).join("\n\n");
          this._draft = {
            name: p.name,
            species: p.species,
            common_name: p.common_name,
            location: p.location,
            water_days: p.water_days,
            fertilize_days: p.fertilize_days,
            moisture_sensor: p.moisture_sensor,
            photo: p.photo,
            light_level: p.light_level || "",
            room_type: p.room_type || "",
            suitability_warning: p.suitability_warning || "",
            plant_description: mergedDesc,
          };
          this._setState({ _view: "edit", _selectedId: id });
        }
        break;
      }
      case "delete":
        this._deletePlant(this._selectedId);
        break;
      case "water":
        this._waterPlant(id);
        break;
      case "fertilize":
        this._fertilizePlant(id);
        break;
      case "ai-suggest":
        evt.preventDefault();
        this._aiSuggestFromName(this._draft?.name || "");
        break;
      case "photo-identify": {
        evt.preventDefault();
        const input = this.shadowRoot.getElementById("photo-identify-input");
        if (input) {
          input.onchange = (e) => {
            const file = e.target.files && e.target.files[0];
            if (file) this._handlePhotoFile(file, { identifyWithAi: true });
          };
          input.click();
        }
        break;
      }
      case "clear-photo":
        this._draft = { ...(this._draft || {}), photo: "" };
        this._render();
        break;
      case "filter-room":
        this._setState({ _roomFilter: target.dataset.room });
        break;
    }
  }

  _onInput(evt) {
    const t = evt.target;
    if (!t.name || t.type === "file") return;
    this._draft = { ...(this._draft || {}), [t.name]: t.value };
    // Kein Re-Render auf jeden Tastendruck (zerstört Cursor).
  }

  _onChange(evt) {
    const t = evt.target;
    if (t.type === "file" && t.name === "photo_file") {
      const file = t.files && t.files[0];
      if (file) this._handlePhotoFile(file, { identifyWithAi: false });
      return;
    }
    if (t.name === "moisture_sensor") {
      this._draft = { ...(this._draft || {}), moisture_sensor: t.value };
    }
    if (t.dataset && t.dataset.action === "set-room") {
      const val = t.value;
      if (val === "__other__") {
        this._draft = { ...(this._draft || {}), room_type: this._draft?.room_type || "" };
      } else {
        this._draft = { ...(this._draft || {}), room_type: val };
      }
      this._render();
      return;
    }
    if (t.name === "room_type_other") {
      this._draft = { ...(this._draft || {}), room_type: t.value };
      return; // Kein Re-Render – sonst Cursor weg
    }
    if (t.name === "light_level") {
      this._draft = { ...(this._draft || {}), light_level: t.value };
    }
  }

  async _onSubmit(evt) {
    evt.preventDefault();
    const form = evt.target;
    const formData = new FormData(form);
    const isEdit = this._view === "edit" && this._selectedId;
    const data = {};
    for (const [k, v] of formData.entries()) {
      if (k === "photo_file") continue;
      // Add-Mode: leere Strings überspringen, damit Backend-Defaults greifen.
      // Edit-Mode: leere Strings durchlassen → User kann Feld explizit leeren.
      if (!isEdit && v === "" && k !== "name") continue;
      data[k] = v;
    }
    // Numerische Felder casten. Leere Eingaben im Edit-Mode entfernen,
    // damit der bestehende Wert erhalten bleibt (kein NaN-Update).
    for (const k of ["water_days", "fertilize_days"]) {
      if (data[k] === "" || data[k] === undefined) {
        delete data[k];
      } else {
        data[k] = parseInt(data[k], 10);
      }
    }
    // Room aus Dropdown/Other-Input zusammenführen
    const roomSelect = formData.get("room_type_select");
    if (roomSelect === "__other__") {
      data.room_type = (formData.get("room_type_other") || "").toString();
    } else if (roomSelect !== null) {
      data.room_type = roomSelect.toString();
    }
    delete data.room_type_select;
    delete data.room_type_other;

    // Q&A-AI-Resultate aus dem Draft übernehmen
    if (this._draft && "suitability_warning" in this._draft) {
      data.suitability_warning = this._draft.suitability_warning || "";
    }
    if (this._draft && "plant_description" in this._draft) {
      data.plant_description = this._draft.plant_description || "";
    }

    // Photo aus Draft übernehmen. Im Edit-Mode bedeutet draft.photo === ""
    // explizit "Foto entfernen".
    if (this._draft && "photo" in this._draft) {
      data.photo = this._draft.photo || "";
    }

    try {
      if (this._view === "edit" && this._selectedId) {
        await this._callService("plant_care", "update_plant", {
          plant_id: this._selectedId,
          ...data,
        });
        this._showToast("success", "Pflanze aktualisiert");
        this._draft = null;
        this._setState({ _view: "detail" });
      } else {
        await this._callService("plant_care", "add_plant", data);
        this._showToast("success", "Pflanze hinzugefügt");
        this._draft = null;
        this._setState({ _view: "list" });
      }
    } catch (err) {
      console.error(err);
      this._showToast("error", "Speichern fehlgeschlagen: " + (err.message || err));
    }
  }

  async _waterPlant(plantId) {
    try {
      await this._callService("plant_care", "water_plant", { plant_id: plantId });
      this._showToast("success", "💧 Markiert als gegossen");
      if (this._view === "calendar") this._loadCalendar();
    } catch (err) {
      this._showToast("error", err.message || String(err));
    }
  }

  async _fertilizePlant(plantId) {
    try {
      await this._callService("plant_care", "fertilize_plant", { plant_id: plantId });
      this._showToast("success", "🌱 Markiert als gedüngt");
      if (this._view === "calendar") this._loadCalendar();
    } catch (err) {
      this._showToast("error", err.message || String(err));
    }
  }

  async _deletePlant(plantId) {
    if (!plantId) return;
    if (!confirm("Pflanze wirklich löschen?")) return;
    try {
      await this._callService("plant_care", "remove_plant", { plant_id: plantId });
      this._showToast("success", "Pflanze gelöscht");
      this._draft = null;
      this._setState({ _view: "list", _selectedId: null });
    } catch (err) {
      this._showToast("error", err.message || String(err));
    }
  }

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

  async _executeBulkAction(serviceName) {
    const ids = Array.from(this._bulkSelection);
    if (ids.length === 0 || this._bulkBusy) return;
    const labels = {
      water_plant: { confirm: "als gegossen", past: "als gegossen" },
      fertilize_plant: { confirm: "als gedüngt", past: "als gedüngt" },
    };
    const label = labels[serviceName];
    if (!label) return;
    if (ids.length > 5) {
      if (!confirm(`${ids.length} Pflanzen ${label.confirm} markieren?`)) return;
    }
    this._bulkBusy = true;
    this._render();
    try {
      await Promise.all(
        ids.map((id) =>
          this._callService("plant_care", serviceName, { plant_id: id }),
        ),
      );
      this._showToast(
        "success",
        `${ids.length} ${ids.length === 1 ? "Pflanze" : "Pflanzen"} ${label.past} markiert`,
      );
      this._bulkSelection.clear();
      this._bulkMode = false;
    } catch (err) {
      this._showToast(
        "error",
        "Bulk-Action fehlgeschlagen: " + this._fmtErr(err),
      );
    } finally {
      this._bulkBusy = false;
      this._setState({});
    }
  }

  /* -------------------------------- Styles ------------------------------- */

  _styles() {
    return `
      :host {
        display: block;
        color: var(--primary-text-color, #1a1a1a);
        background: var(--primary-background-color, #f5f7f3);
        --sage: #6b8f5e;
        --sage-light: #9ec789;
        --sage-bg: #f0f5ec;
      }
      .app {
        max-width: 1100px;
        margin: 0 auto;
        padding: 16px;
        min-height: 100vh;
        box-sizing: border-box;
      }
      .topbar {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 16px;
        flex-wrap: nowrap;
      }
      .topbar-spacer { flex: 1; min-width: 4px; }
      .topbar-actions {
        display: flex;
        align-items: center;
        gap: 4px;
        padding: 2px;
        border-radius: 22px;
        background: var(--secondary-background-color, rgba(255,255,255,0.04));
      }
      .brand { display: flex; align-items: center; gap: 8px; min-width: 0; }
      .brand h1 { margin: 0; font-size: 1.35rem; font-weight: 600; white-space: nowrap; }
      .brand .leaf { font-size: 1.6rem; }

      .icon-btn {
        width: 40px;
        height: 40px;
        border-radius: 50%;
        border: none;
        background: transparent;
        cursor: pointer;
        font-size: 1.1rem;
        line-height: 1;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 0;
        color: inherit;
        font-family: inherit;
        transition: background .15s, transform .08s;
      }
      .icon-btn:hover { background: var(--sage-bg); }
      .icon-btn:active { transform: scale(0.94); }
      .icon-btn.ha-menu {
        flex-shrink: 0;
      }
      .topbar .cta {
        flex-shrink: 0;
        padding: 9px 16px;
        font-weight: 600;
      }
      .muted { color: var(--secondary-text-color, #777); }
      .small { font-size: 0.85rem; }

      .btn {
        border: 1px solid var(--divider-color, #d4d4d4);
        background: var(--card-background-color, #fff);
        color: inherit;
        padding: 8px 14px;
        border-radius: 8px;
        cursor: pointer;
        font-size: 0.95rem;
        font-family: inherit;
        transition: background .15s, transform .05s;
      }
      .btn:hover:not(:disabled) { background: var(--sage-bg); }
      .btn:active:not(:disabled) { transform: scale(0.98); }
      .btn.primary {
        background: var(--sage);
        color: white;
        border-color: var(--sage);
      }
      .btn.primary:hover { background: var(--sage-light); }
      .btn.ghost { background: transparent; }
      .btn.danger { color: var(--error-color, #c92a2a); border-color: var(--error-color, #c92a2a); }
      .btn.danger:hover { background: rgba(201,42,42,0.08); }
      .btn.small { padding: 4px 10px; font-size: 0.85rem; }
      .btn.disabled, .btn:disabled { opacity: 0.5; cursor: not-allowed; }

      .toast {
        position: fixed;
        top: 16px;
        right: 16px;
        padding: 10px 14px;
        border-radius: 8px;
        color: white;
        z-index: 100;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        animation: slideIn .2s ease-out;
      }
      .toast.success { background: var(--sage); }
      .toast.error { background: var(--error-color, #c92a2a); }
      .toast.info { background: var(--info-color, #1971c2); }
      @keyframes slideIn {
        from { transform: translateX(20px); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
      }

      .rooms {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin-bottom: 12px;
      }
      .room {
        background: var(--card-background-color, #fff);
        border: 1px solid var(--divider-color, #d4d4d4);
        border-radius: 999px;
        padding: 6px 14px;
        cursor: pointer;
        font-family: inherit;
        font-size: 0.9rem;
        color: inherit;
      }
      .room.active { background: var(--sage); color: white; border-color: var(--sage); }

      .grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
        gap: 12px;
      }
      .list-compact {
        display: flex;
        flex-direction: column;
        gap: 8px;
      }
      .row-card {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 10px 12px;
        background: var(--card-background-color, #fff);
        border: 1px solid var(--divider-color, #e8e8e8);
        border-radius: 12px;
        cursor: pointer;
        transition: transform .1s, box-shadow .15s;
        position: relative;
      }
      .row-card:hover {
        transform: translateY(-1px);
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
      }
      .row-card.bulk { user-select: none; }
      .row-card.bulk.selected {
        outline: 3px solid var(--sage);
        outline-offset: -3px;
      }
      .row-photo {
        flex: 0 0 56px;
        width: 56px;
        height: 56px;
        border-radius: 50%;
        overflow: hidden;
        background: var(--sage-bg);
      }
      .row-photo img { width: 100%; height: 100%; object-fit: cover; }
      .row-info {
        flex: 1;
        min-width: 0;
        display: flex;
        flex-direction: column;
        gap: 2px;
      }
      .row-title {
        font-weight: 600;
        font-size: 1rem;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .row-meta {
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
      }
      .row-meta .status { margin: 0; padding: 2px 8px; font-size: 0.75rem; }
      .row-actions {
        display: flex;
        gap: 6px;
        flex-shrink: 0;
      }
      .thumb-placeholder.small { font-size: 1.6rem; }
      .card {
        background: var(--card-background-color, #fff);
        border: 1px solid var(--divider-color, #e8e8e8);
        border-radius: 12px;
        overflow: hidden;
        cursor: pointer;
        transition: transform .1s, box-shadow .15s;
        position: relative;
      }
      .card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
      }
      .card.bulk { cursor: pointer; user-select: none; }
      .card.bulk.selected {
        outline: 3px solid var(--sage);
        outline-offset: -3px;
      }
      .bulk-check {
        position: absolute;
        top: 10px;
        left: 10px;
        width: 28px;
        height: 28px;
        border-radius: 50%;
        background: var(--card-background-color, #fff);
        border: 2px solid var(--sage);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1rem;
        font-weight: 700;
        color: var(--sage);
        z-index: 2;
        box-shadow: 0 2px 6px rgba(0,0,0,0.15);
      }
      .bulk-check.checked { background: var(--sage); color: #fff; }
      .bulk-bar {
        position: sticky;
        bottom: 0;
        margin-top: 16px;
        background: var(--card-background-color, #fff);
        border-top: 1px solid var(--divider-color, rgba(0,0,0,0.1));
        box-shadow: 0 -4px 16px rgba(0,0,0,0.08);
        padding: 12px 16px;
        display: flex;
        align-items: center;
        gap: 16px;
        flex-wrap: wrap;
        z-index: 5;
      }
      .bulk-bar-select-all {
        display: flex;
        align-items: center;
        gap: 6px;
        cursor: pointer;
        user-select: none;
      }
      .bulk-bar-select-all input[type="checkbox"] {
        width: 18px;
        height: 18px;
        accent-color: var(--sage);
      }
      .bulk-bar-count {
        flex: 1 1 auto;
        color: var(--secondary-text-color, #777);
        font-size: 0.9rem;
        min-width: 0;
      }
      .bulk-bar-actions {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
      }

      .location-grid { margin-bottom: 8px; }
      .radio-group {
        display: flex;
        flex-direction: column;
        gap: 6px;
      }
      .radio-pill {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 7px 10px;
        border: 1px solid var(--divider-color, rgba(255,255,255,0.1));
        border-radius: 8px;
        background: var(--secondary-background-color, rgba(255,255,255,0.02));
        font-size: 0.88rem;
        cursor: pointer;
        transition: background .12s, border-color .12s;
      }
      .radio-pill:hover { border-color: var(--sage); }
      .radio-pill:has(input:checked) {
        background: rgba(126, 174, 110, 0.14);
        border-color: var(--sage);
      }
      .radio-pill input[type="radio"] {
        accent-color: var(--sage);
        margin: 0;
      }
      .radio-pill span { line-height: 1.2; }
      .location-tips-card {
        margin: 12px 0;
        display: flex;
        flex-direction: column;
        gap: 8px;
      }
      .info-banner,
      .warning-banner {
        border-radius: 8px;
        padding: 10px 12px;
      }
      .info-banner {
        background: rgba(126, 174, 110, 0.12);
        border-left: 3px solid var(--sage);
      }
      .info-banner strong { display: block; margin-bottom: 4px; }
      .info-banner p { margin: 0; white-space: pre-wrap; }
      .warning-banner {
        background: rgba(245, 158, 11, 0.12);
        border-left: 3px solid #f59e0b;
      }
      .warning-banner strong { display: block; margin-bottom: 4px; color: #b45309; }
      .warning-banner p { margin: 0; white-space: pre-wrap; }
      .wiki-section {
        margin-bottom: 16px;
        padding: 12px 14px;
        border-radius: 10px;
        background: rgba(126, 174, 110, 0.06);
        border: 1px solid rgba(126, 174, 110, 0.25);
      }
      .wiki-section h3 { margin: 0 0 6px; font-size: 1rem; }
      .wiki-section p {
        margin: 0;
        white-space: pre-wrap;
        line-height: 1.45;
        font-size: 0.95rem;
      }

      .care-location-section {
        margin-bottom: 20px;
      }
      .care-location-section h3 { margin: 0 0 8px; font-size: 1rem; }
      .care-location-facts { margin: 0 0 10px; }
      .care-location-section .info-banner + .info-banner { margin-top: 8px; }
      .detail-warning {
        position: relative;
        margin-bottom: 16px;
      }
      .warning-dismiss {
        position: absolute;
        top: 6px;
        right: 8px;
        background: none;
        border: none;
        font-size: 1rem;
        cursor: pointer;
        color: var(--secondary-text-color, #777);
        line-height: 1;
        padding: 4px 6px;
      }
      .warning-dismiss:hover { color: var(--primary-text-color); }

      .status.attention { background: rgba(245, 158, 11, 0.15); color: #b45309; }

      .treatments { margin-bottom: 20px; }
      .treatments h3 { margin: 0 0 8px; font-size: 1rem; }
      .treatment-actions { margin-bottom: 8px; }
      .treatment-card {
        background: rgba(245, 158, 11, 0.08);
        border-left: 3px solid #f59e0b;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
      }
      .treatment-card.closed {
        background: rgba(0,0,0,0.04);
        border-left-color: var(--sage);
        opacity: 0.85;
      }
      .treatment-card header {
        display: flex;
        align-items: center;
        gap: 6px;
        margin-bottom: 6px;
        flex-wrap: wrap;
      }
      .treatment-icon { font-size: 1.1rem; }
      .treatment-steps { margin: 8px 0; padding-left: 20px; }
      .treatment-steps li { margin: 2px 0; }
      .treatment-actions-row { display: flex; gap: 8px; margin-top: 8px; }
      .closed-treatments { margin-top: 12px; }
      .closed-treatments summary { cursor: pointer; padding: 4px 0; }
      .diagnose-body {
        padding: 16px;
        background: var(--card-background-color, #fff);
        max-height: 60vh;
        overflow-y: auto;
      }
      .diagnose-body .error { color: var(--error-color, #c92a2a); }
      .diagnose-mode-choice {
        display: flex;
        flex-direction: column;
        gap: 10px;
        margin-top: 8px;
      }
      .diagnose-mode-choice .btn {
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        gap: 2px;
        padding: 14px 16px;
        text-align: left;
      }
      .diagnose-mode-choice .btn small {
        font-weight: 400;
        opacity: 0.8;
        font-size: 0.85rem;
      }
      .manual-diagnose .field { margin-bottom: 10px; }
      .manual-diagnose textarea,
      .manual-diagnose input,
      .manual-diagnose select {
        width: 100%;
        font-family: inherit;
        font-size: 0.95rem;
        padding: 8px;
        border-radius: 6px;
        border: 1px solid var(--divider-color, #d4d4d4);
        background: var(--secondary-background-color, #fff);
        color: inherit;
        box-sizing: border-box;
      }

      /* Agenda / Calendar */
      .agenda-loading {
        padding: 40px 16px;
        text-align: center;
        color: var(--secondary-text-color, #777);
      }
      .agenda {
        display: flex;
        flex-direction: column;
        gap: 14px;
      }
      .agenda-day {
        background: var(--card-background-color, #fff);
        border: 1px solid var(--divider-color, rgba(255,255,255,0.08));
        border-radius: 10px;
        padding: 12px 14px;
      }
      .agenda-day.today {
        border-left: 3px solid var(--sage);
        background: rgba(126, 174, 110, 0.06);
      }
      .agenda-day-label {
        font-size: 0.82rem;
        font-weight: 600;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: var(--sage);
        margin: 0 0 10px;
      }
      .agenda-events {
        list-style: none;
        margin: 0;
        padding: 0;
        display: flex;
        flex-direction: column;
        gap: 6px;
      }
      .agenda-event {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 8px 10px;
        border-radius: 8px;
        background: var(--secondary-background-color, rgba(255,255,255,0.02));
        border: 1px solid var(--divider-color, rgba(255,255,255,0.06));
      }
      .agenda-event.overdue {
        border-left: 3px solid #f59e0b;
        background: rgba(245, 158, 11, 0.06);
      }
      .agenda-event-main {
        flex: 1 1 auto;
        display: flex;
        align-items: center;
        gap: 8px;
        background: none;
        border: 0;
        padding: 0;
        cursor: pointer;
        color: inherit;
        font: inherit;
        text-align: left;
        min-width: 0;
      }
      .agenda-event-main:hover .agenda-event-name { text-decoration: underline; }
      .agenda-photo {
        position: relative;
        flex: 0 0 44px;
        width: 44px;
        height: 44px;
        border-radius: 50%;
        overflow: hidden;
        background: var(--sage-bg);
        display: inline-flex;
        align-items: center;
        justify-content: center;
      }
      .agenda-photo img {
        width: 100%;
        height: 100%;
        object-fit: cover;
      }
      .agenda-photo-badge {
        position: absolute;
        bottom: -2px;
        right: -2px;
        width: 22px;
        height: 22px;
        border-radius: 50%;
        background: var(--card-background-color, #fff);
        border: 2px solid var(--card-background-color, #fff);
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 0.85rem;
        line-height: 1;
        overflow: visible;
      }
      .agenda-icon { font-size: 1.15rem; line-height: 1; }
      .agenda-event-info {
        flex: 1 1 auto;
        min-width: 0;
        display: flex;
        flex-direction: column;
        gap: 1px;
      }
      .agenda-event-name {
        font-weight: 500;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .agenda-event-action { flex: 0 0 auto; }
      .agenda-overdue {
        flex: 0 0 auto;
        font-size: 0.72rem;
        font-weight: 600;
        color: #b45309;
        letter-spacing: 0.04em;
        text-transform: uppercase;
      }
      .agenda-action-btn { flex: 0 0 auto; }
      .agenda-footer {
        margin-top: 8px;
        text-align: center;
      }

      .photo-history { margin-bottom: 20px; }
      .photo-history h3 { margin: 0 0 8px; font-size: 1rem; }
      .photo-actions { margin-bottom: 12px; }
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
      .photo-thumb:hover { border-color: var(--sage); }
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

      .thumb {
        width: 100%;
        aspect-ratio: 16 / 10;
        overflow: hidden;
        background: var(--sage-bg);
      }
      .thumb img {
        width: 100%; height: 100%; object-fit: cover; display: block;
      }
      .thumb-placeholder {
        width: 100%; height: 100%; display: flex; align-items: center;
        justify-content: center; font-size: 3rem; color: var(--sage-light);
      }
      .thumb-placeholder.large { font-size: 5rem; }
      .card-body { padding: 12px; }
      .card-body h3 { margin: 0 0 4px; font-size: 1.05rem; }
      .card-body p { margin: 2px 0; }
      .card-footer {
        display: flex;
        align-items: flex-end;
        justify-content: space-between;
        gap: 8px;
        margin-top: 6px;
      }
      .card-status { min-width: 0; flex: 1; }
      .card-actions {
        display: flex;
        gap: 6px;
        flex-shrink: 0;
      }
      .card-action-btn {
        width: 36px;
        height: 36px;
        border-radius: 50%;
        border: 1px solid var(--divider-color, #e8e8e8);
        background: var(--sage-bg);
        font-size: 1.1rem;
        line-height: 1;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 0;
        transition: transform .1s, background .15s;
      }
      .card-action-btn:hover {
        background: var(--sage);
        transform: scale(1.05);
      }
      .card-action-btn:active { transform: scale(0.95); }

      .status {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 999px;
        font-size: 0.8rem;
        margin: 6px 0;
        font-weight: 500;
      }
      .status.ok { background: var(--sage-bg); color: var(--sage); }
      .status.water { background: #e3f2fd; color: #1565c0; }
      .status.fert { background: #fff4e5; color: #b86604; }
      .status.both { background: #fde8e8; color: #c92a2a; }

      .empty {
        text-align: center;
        padding: 60px 20px;
      }
      .empty h2 { margin: 16px 0 8px; }
      .empty .btn { margin-top: 16px; }

      .page-title { margin: 0 0 16px; }
      form {
        background: var(--card-background-color, #fff);
        border: 1px solid var(--divider-color, #e8e8e8);
        border-radius: 12px;
        padding: 20px;
      }
      /* Form-Sections – setzen thematisch zusammengehörige Felder ab. */
      .form-section {
        position: relative;
        padding: 16px 18px 4px;
        margin-bottom: 14px;
        background: var(--secondary-background-color, rgba(255,255,255,0.03));
        border: 1px solid var(--divider-color, rgba(255,255,255,0.08));
        border-radius: 10px;
        border-left: 3px solid var(--sage);
      }
      .form-section-head {
        display: flex;
        align-items: baseline;
        gap: 8px;
        margin-bottom: 12px;
      }
      .form-section-label {
        font-size: 0.78rem;
        font-weight: 600;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        color: var(--sage);
      }
      .form-section-hint {
        font-size: 0.72rem;
        color: var(--secondary-text-color, #777);
        letter-spacing: 0.04em;
      }

      .ai-actions {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin-bottom: 4px;
      }

      .form-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 12px 14px;
        margin-bottom: 4px;
      }
      .form-grid-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .form-grid-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      @media (max-width: 640px) {
        .form-grid-2, .form-grid-3 { grid-template-columns: 1fr; }
      }

      .field {
        display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px;
        min-width: 0;
      }
      .field > span, .field-label {
        font-size: 0.9rem;
        font-weight: 500;
        display: block;
      }
      input, select, textarea {
        font-family: inherit;
        font-size: 1rem;
        padding: 8px 10px;
        border: 1px solid var(--divider-color, #d4d4d4);
        border-radius: 6px;
        background: var(--secondary-background-color, #fff);
        color: inherit;
      }
      input:focus, select:focus, textarea:focus {
        outline: 2px solid var(--sage-light);
        outline-offset: 1px;
      }
      textarea { resize: vertical; min-height: 60px; }

      .photo-preview {
        margin-top: 8px;
        display: flex;
        align-items: flex-start;
        gap: 8px;
      }
      .photo-preview img {
        max-width: 200px;
        border-radius: 8px;
        border: 1px solid var(--divider-color, #d4d4d4);
      }

      .actions {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin-top: 18px;
        padding-top: 16px;
        border-top: 1px solid var(--divider-color, rgba(255,255,255,0.08));
      }
      .actions .danger { margin-left: auto; }

      .detail {
        background: var(--card-background-color, #fff);
        border: 1px solid var(--divider-color, #e8e8e8);
        border-radius: 12px;
        padding: 20px;
      }
      .detail-header {
        display: flex; gap: 20px; align-items: flex-start;
        margin-bottom: 20px; flex-wrap: wrap;
      }
      .detail-photo {
        flex: 0 0 220px;
        aspect-ratio: 1;
        border-radius: 12px;
        overflow: hidden;
        background: var(--sage-bg);
      }
      .detail-photo img { width: 100%; height: 100%; object-fit: cover; }
      .detail-meta { flex: 1 1 240px; min-width: 0; }
      .detail-meta h2 { margin: 0 0 2px; line-height: 1.2; }
      .detail-meta p { margin: 2px 0; line-height: 1.3; }
      .detail-meta .species { font-style: italic; }
      .detail-meta .facts {
        display: flex;
        flex-wrap: wrap;
        gap: 2px 14px;
      }
      .detail-meta .meta-row {
        display: flex;
        align-items: center;
        gap: 10px;
        flex-wrap: wrap;
        margin-top: 8px;
      }
      .detail-meta .meta-row .status { margin: 0; }

      .quick-actions {
        display: flex;
        gap: 12px;
        margin-bottom: 22px;
      }
      .quick-action.btn {
        flex: 1;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 10px;
        padding: 14px 16px;
        min-width: 0;
        border-radius: 14px;
        border: none;
        font-size: 1rem;
        font-weight: 600;
        letter-spacing: 0.02em;
        color: #fff;
        background: linear-gradient(135deg, var(--sage) 0%, var(--sage-light, #8fb392) 100%);
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08), inset 0 1px 0 rgba(255, 255, 255, 0.18);
        cursor: pointer;
        transition: transform .12s ease, box-shadow .15s ease, filter .15s ease;
      }
      .quick-action.btn:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.18);
        filter: brightness(1.04);
      }
      .quick-action.btn:active {
        transform: translateY(0);
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12), inset 0 1px 2px rgba(0, 0, 0, 0.1);
      }
      .quick-action .qa-icon {
        font-size: 1.35rem;
        line-height: 1;
        filter: drop-shadow(0 1px 1px rgba(0, 0, 0, 0.15));
      }
      .quick-action .qa-label { font-weight: 600; }
      .quick-action .qa-meta {
        margin-left: auto;
        font-size: 0.78rem;
        font-weight: 500;
        opacity: 0.85;
        padding: 3px 8px;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.18);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .moisture-section {
        background: var(--secondary-background-color, #fafafa);
        border: 1px solid var(--divider-color, #e8e8e8);
        border-radius: 10px;
        padding: 14px;
        margin-bottom: 20px;
      }
      .moisture-section h3 { margin: 0 0 8px; font-size: 1rem; }

      .moisture-bar {
        position: relative;
        height: 24px;
        background: var(--divider-color, #e8e8e8);
        border-radius: 12px;
        overflow: hidden;
        margin: 8px 0;
      }
      .moisture-fill {
        height: 100%;
        background: linear-gradient(90deg, var(--sage), var(--sage-light));
        transition: width .3s;
      }
      .moisture-label {
        position: absolute;
        top: 0; left: 0; right: 0; bottom: 0;
        display: flex; align-items: center; justify-content: center;
        font-size: 0.85rem; font-weight: 600;
        color: var(--primary-text-color, #fff);
        mix-blend-mode: difference;
      }

      .history h3 { margin: 0 0 12px; font-size: 1rem; }
      .chart-row {
        display: flex; align-items: center; gap: 12px;
        margin-bottom: 8px; flex-wrap: wrap;
      }
      .chart-label {
        flex: 0 0 140px; font-size: 0.9rem;
      }
      .chart {
        flex: 1 1 240px;
        height: 50px;
        max-width: 100%;
      }
      .chart-axis {
        flex-basis: 100%;
        display: flex; justify-content: space-between;
        font-size: 0.75rem;
        color: var(--secondary-text-color, #777);
        margin-left: 152px;
      }

      @media (max-width: 640px) {
        .topbar h1 { font-size: 1.1rem; }
        .topbar .cta { padding: 8px 12px; font-size: 0.9rem; }
        .detail-photo { flex-basis: 100%; aspect-ratio: 16 / 10; }
        .chart-axis { margin-left: 0; }
        .chart-label { flex-basis: auto; }
      }
      @media (max-width: 480px) {
        .brand h1 { display: none; }
      }
      @media (max-width: 420px) {
        .quick-action .qa-meta { display: none; }
      }
    `;
  }
}

if (!customElements.get("plant-care-panel")) {
  customElements.define("plant-care-panel", PlantCarePanel);
}
