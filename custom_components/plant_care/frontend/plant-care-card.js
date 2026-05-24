/**
 * Plant Care – Lovelace Custom Card
 *
 * Verwendung in Lovelace:
 *   type: custom:plant-care-card
 *   entity: sensor.plant_monstera
 *
 * Resource-Registration:
 *   /plant_care_frontend/plant-care-card.js (Type: JavaScript-Modul)
 */

const STATUS_LABEL = {
  ok: "Alles gut",
  needs_water: "Braucht Wasser",
  needs_fertilizer: "Braucht Dünger",
  needs_both: "Wasser + Dünger",
};

const STATUS_COLOR = {
  ok: "#6b8f5e",
  needs_water: "#1565c0",
  needs_fertilizer: "#b86604",
  needs_both: "#c92a2a",
};

class PlantCareCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._lastSig = "";
    this._onWaterClick = this._onWaterClick.bind(this);
    this._onFertilizeClick = this._onFertilizeClick.bind(this);
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("'entity' ist erforderlich (sensor.plant_*)");
    }
    this._config = config;
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  static getStubConfig(hass) {
    const ids = Object.keys(hass?.states || {}).filter((id) =>
      id.startsWith("sensor.plant_"),
    );
    return { entity: ids[0] || "sensor.plant_example" };
  }

  static getConfigElement() {
    return null;
  }

  getCardSize() {
    return 3;
  }

  _escape(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]),
    );
  }

  _relativeTime(iso) {
    if (!iso) return "noch nie";
    const t = Date.parse(iso);
    if (Number.isNaN(t)) return "–";
    const diffMs = Date.now() - t;
    const days = Math.floor(diffMs / 86400000);
    if (days < 1) return "heute";
    if (days === 1) return "gestern";
    if (days < 30) return `vor ${days} Tagen`;
    const months = Math.floor(days / 30);
    return `vor ${months} Monat${months === 1 ? "" : "en"}`;
  }

  _render() {
    if (!this._hass || !this._config) return;
    const state = this._hass.states[this._config.entity];
    if (!state) {
      this.shadowRoot.innerHTML = `
        <style>${this._styles()}</style>
        <ha-card><div class="error">Entity nicht gefunden: ${this._escape(this._config.entity)}</div></ha-card>
      `;
      return;
    }
    const a = state.attributes || {};
    const status = state.state || "ok";
    const sig = `${state.entity_id}|${status}|${a.last_watered}|${a.last_fertilized}|${a.moisture_pct}|${a.photo ? "p" : ""}`;
    if (sig === this._lastSig) return;
    this._lastSig = sig;

    const moisture =
      typeof a.moisture_pct === "number"
        ? Math.max(0, Math.min(100, a.moisture_pct))
        : null;

    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <ha-card>
        <div class="container">
          <div class="thumb">
            ${a.photo
              ? `<img src="${this._escape(a.photo)}" alt="">`
              : `<div class="placeholder">🌱</div>`}
          </div>
          <div class="body">
            <h2>${this._escape(a.name || state.entity_id)}</h2>
            ${a.species ? `<p class="muted">${this._escape(a.species)}</p>` : ""}
            <p class="status" style="--c:${STATUS_COLOR[status] || "#777"}">
              ${this._escape(STATUS_LABEL[status] || status)}
            </p>
            <div class="meta">
              <span>💧 ${this._escape(this._relativeTime(a.last_watered))}</span>
              <span>🌱 ${this._escape(this._relativeTime(a.last_fertilized))}</span>
            </div>
            ${moisture !== null ? `
              <div class="bar">
                <div class="fill" style="width:${moisture}%"></div>
                <span>${Math.round(moisture)}%</span>
              </div>
            ` : ""}
            <div class="actions">
              <button class="btn" id="btn-water">💧 Gegossen</button>
              <button class="btn" id="btn-fert">🌱 Gedüngt</button>
            </div>
          </div>
        </div>
      </ha-card>
    `;
    this.shadowRoot.getElementById("btn-water").addEventListener("click", this._onWaterClick);
    this.shadowRoot.getElementById("btn-fert").addEventListener("click", this._onFertilizeClick);
  }

  async _onWaterClick() {
    const a = this._hass.states[this._config.entity]?.attributes || {};
    if (!a.plant_id) return;
    await this._hass.callService("plant_care", "water_plant", { plant_id: a.plant_id });
  }

  async _onFertilizeClick() {
    const a = this._hass.states[this._config.entity]?.attributes || {};
    if (!a.plant_id) return;
    await this._hass.callService("plant_care", "fertilize_plant", { plant_id: a.plant_id });
  }

  _styles() {
    return `
      :host { display: block; }
      ha-card {
        padding: 0;
        overflow: hidden;
      }
      .container {
        display: flex;
        gap: 12px;
        padding: 12px;
      }
      .thumb {
        flex: 0 0 96px;
        height: 96px;
        border-radius: 8px;
        overflow: hidden;
        background: #f0f5ec;
      }
      .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
      .placeholder {
        width: 100%; height: 100%;
        display: flex; align-items: center; justify-content: center;
        font-size: 2.5rem; color: #9ec789;
      }
      .body { flex: 1 1 auto; min-width: 0; }
      .body h2 { margin: 0 0 2px; font-size: 1.05rem; }
      .muted { color: var(--secondary-text-color, #777); font-size: 0.85rem; margin: 0 0 4px; }
      .status {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 999px;
        font-size: 0.8rem;
        font-weight: 500;
        background: color-mix(in srgb, var(--c) 15%, transparent);
        color: var(--c);
        margin: 4px 0;
      }
      .meta {
        display: flex; gap: 12px;
        font-size: 0.85rem;
        color: var(--secondary-text-color, #777);
        margin: 4px 0;
      }
      .bar {
        position: relative;
        height: 18px;
        background: var(--divider-color, #e0e0e0);
        border-radius: 9px;
        overflow: hidden;
        margin: 6px 0;
      }
      .fill {
        height: 100%;
        background: linear-gradient(90deg, #6b8f5e, #9ec789);
      }
      .bar span {
        position: absolute; top: 0; left: 0; right: 0; bottom: 0;
        display: flex; align-items: center; justify-content: center;
        font-size: 0.75rem; font-weight: 600;
        mix-blend-mode: difference;
        color: white;
      }
      .actions {
        display: flex; gap: 6px;
        margin-top: 8px;
      }
      .btn {
        flex: 1 1 auto;
        background: var(--card-background-color, #fff);
        border: 1px solid var(--divider-color, #d4d4d4);
        border-radius: 6px;
        padding: 6px 8px;
        cursor: pointer;
        font-family: inherit;
        font-size: 0.85rem;
        color: inherit;
      }
      .btn:hover { background: #f0f5ec; }
      .error {
        padding: 16px;
        color: var(--error-color, #c92a2a);
      }
    `;
  }
}

if (!customElements.get("plant-care-card")) {
  customElements.define("plant-care-card", PlantCareCard);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "plant-care-card",
  name: "Plant Care Card",
  description: "Zeigt eine Pflanze aus Plant Care kompakt an",
  preview: false,
  documentationURL: "https://github.com/fhb1997/HA_Pflanzen_App",
});
