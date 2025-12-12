/**
 * Lionel Train Controller Card
 * A custom Lovelace card for controlling Lionel LionChief trains
 */

class LionelTrainCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
  }

  set hass(hass) {
    this._hass = hass;
    this._updateCard();
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error('You need to define an entity (the throttle number entity)');
    }
    this._config = config;
    this._entityBase = config.entity.replace('_throttle', '').replace('number.', '');
    this._render();
  }

  _getEntityId(suffix) {
    return `${this._entityBase}_${suffix}`;
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          --card-bg: var(--ha-card-background, var(--card-background-color, white));
          --primary-color: var(--primary-color, #03a9f4);
          --text-color: var(--primary-text-color, #212121);
          --secondary-text: var(--secondary-text-color, #727272);
        }
        
        .card {
          background: var(--card-bg);
          border-radius: 12px;
          padding: 16px;
          font-family: var(--paper-font-body1_-_font-family, 'Roboto', sans-serif);
        }
        
        .header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 16px;
        }
        
        .title {
          font-size: 1.2em;
          font-weight: 500;
          color: var(--text-color);
          display: flex;
          align-items: center;
          gap: 8px;
        }
        
        .title svg {
          width: 24px;
          height: 24px;
        }
        
        .status {
          font-size: 0.85em;
          padding: 4px 12px;
          border-radius: 12px;
          font-weight: 500;
        }
        
        .status.connected {
          background: #4caf50;
          color: white;
        }
        
        .status.disconnected {
          background: #f44336;
          color: white;
        }
        
        .throttle-section {
          margin: 20px 0;
        }
        
        .throttle-label {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 8px;
          color: var(--text-color);
        }
        
        .speed-value {
          font-size: 2em;
          font-weight: bold;
          color: var(--primary-color);
        }
        
        .throttle-slider {
          width: 100%;
          height: 40px;
          -webkit-appearance: none;
          appearance: none;
          background: linear-gradient(to right, #4caf50, #ffeb3b, #f44336);
          border-radius: 20px;
          outline: none;
          cursor: pointer;
        }
        
        .throttle-slider::-webkit-slider-thumb {
          -webkit-appearance: none;
          appearance: none;
          width: 50px;
          height: 50px;
          background: white;
          border: 4px solid var(--primary-color);
          border-radius: 50%;
          cursor: grab;
          box-shadow: 0 2px 10px rgba(0,0,0,0.2);
        }
        
        .throttle-slider::-moz-range-thumb {
          width: 50px;
          height: 50px;
          background: white;
          border: 4px solid var(--primary-color);
          border-radius: 50%;
          cursor: grab;
          box-shadow: 0 2px 10px rgba(0,0,0,0.2);
        }
        
        .controls {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 8px;
          margin-top: 16px;
        }
        
        .control-btn {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 12px 8px;
          border: none;
          border-radius: 12px;
          background: var(--ha-card-background, #f5f5f5);
          color: var(--text-color);
          cursor: pointer;
          transition: all 0.2s ease;
          min-height: 70px;
        }
        
        .control-btn:hover {
          background: var(--primary-color);
          color: white;
          transform: scale(1.02);
        }
        
        .control-btn:active {
          transform: scale(0.98);
        }
        
        .control-btn.active {
          background: var(--primary-color);
          color: white;
        }
        
        .control-btn svg {
          width: 28px;
          height: 28px;
          margin-bottom: 4px;
        }
        
        .control-btn span {
          font-size: 0.75em;
          font-weight: 500;
        }
        
        .direction-section {
          display: flex;
          gap: 8px;
          margin-top: 16px;
        }
        
        .direction-btn {
          flex: 1;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          padding: 16px;
          border: 2px solid var(--primary-color);
          border-radius: 12px;
          background: transparent;
          color: var(--primary-color);
          font-size: 1em;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s ease;
        }
        
        .direction-btn:hover, .direction-btn.active {
          background: var(--primary-color);
          color: white;
        }
        
        .direction-btn svg {
          width: 24px;
          height: 24px;
        }
        
        .stop-btn {
          width: 100%;
          padding: 16px;
          margin-top: 16px;
          border: none;
          border-radius: 12px;
          background: #f44336;
          color: white;
          font-size: 1.1em;
          font-weight: bold;
          cursor: pointer;
          transition: all 0.2s ease;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
        }
        
        .stop-btn:hover {
          background: #d32f2f;
          transform: scale(1.02);
        }
        
        .stop-btn:active {
          transform: scale(0.98);
        }
        
        .stop-btn svg {
          width: 24px;
          height: 24px;
        }
        
        .unavailable {
          opacity: 0.5;
          pointer-events: none;
        }
      </style>
      
      <ha-card>
        <div class="card">
          <div class="header">
            <div class="title">
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M12,4L3,7L4.5,8.5L3,10V11H21V10L19.5,8.5L21,7L12,4M3,12V15H5V19H3V21H21V19H19V15H21V12H3M7,15H9V19H7V15M11,15H13V19H11V15M15,15H17V19H15V15Z"/>
              </svg>
              <span>${this._config.name || 'Lionel Train'}</span>
            </div>
            <div class="status disconnected" id="status">Disconnected</div>
          </div>
          
          <div class="throttle-section">
            <div class="throttle-label">
              <span>Throttle</span>
              <span class="speed-value" id="speed-display">0%</span>
            </div>
            <input type="range" class="throttle-slider" id="throttle" min="0" max="100" value="0">
          </div>
          
          <div class="direction-section">
            <button class="direction-btn" id="btn-reverse">
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M20,11V13H8L13.5,18.5L12.08,19.92L4.16,12L12.08,4.08L13.5,5.5L8,11H20Z"/>
              </svg>
              Reverse
            </button>
            <button class="direction-btn" id="btn-forward">
              Forward
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M4,11V13H16L10.5,18.5L11.92,19.92L19.84,12L11.92,4.08L10.5,5.5L16,11H4Z"/>
              </svg>
            </button>
          </div>
          
          <div class="controls">
            <button class="control-btn" id="btn-lights">
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M12,2A7,7 0 0,0 5,9C5,11.38 6.19,13.47 8,14.74V17A1,1 0 0,0 9,18H15A1,1 0 0,0 16,17V14.74C17.81,13.47 19,11.38 19,9A7,7 0 0,0 12,2M9,21A1,1 0 0,0 10,22H14A1,1 0 0,0 15,21V20H9V21Z"/>
              </svg>
              <span>Lights</span>
            </button>
            <button class="control-btn" id="btn-horn">
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M12,1C7,1 3,5 3,10V17A3,3 0 0,0 6,20H9V12H5V10A7,7 0 0,1 12,3A7,7 0 0,1 19,10V12H15V20H18A3,3 0 0,0 21,17V10C21,5 17,1 12,1Z"/>
              </svg>
              <span>Horn</span>
            </button>
            <button class="control-btn" id="btn-bell">
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M21,19V20H3V19L5,17V11C5,7.9 7.03,5.17 10,4.29C10,4.19 10,4.1 10,4A2,2 0 0,1 12,2A2,2 0 0,1 14,4C14,4.1 14,4.19 14,4.29C16.97,5.17 19,7.9 19,11V17L21,19M14,21A2,2 0 0,1 12,23A2,2 0 0,1 10,21"/>
              </svg>
              <span>Bell</span>
            </button>
            <button class="control-btn" id="btn-disconnect">
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M13,8A4,4 0 0,1 9,12A4,4 0 0,1 5,8A4,4 0 0,1 9,4A4,4 0 0,1 13,8M17,18V20H1V18C1,15.79 4.58,14 9,14C13.42,14 17,15.79 17,18M20.5,14.5V16H19V14.5H20.5M18.5,9.5H17V9A3,3 0 0,1 20,6A3,3 0 0,1 23,9C23,9.97 22.5,10.88 21.71,11.41L21.41,11.6C20.84,12 20.5,12.61 20.5,13.3V13.5H19V13.3C19,12.11 19.6,11 20.59,10.35L20.88,10.16C21.27,9.9 21.5,9.47 21.5,9A1.5,1.5 0 0,0 20,7.5A1.5,1.5 0 0,0 18.5,9V9.5Z"/>
              </svg>
              <span>Disconnect</span>
            </button>
          </div>
          
          <button class="stop-btn" id="btn-stop">
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M18,18H6V6H18V18Z"/>
            </svg>
            EMERGENCY STOP
          </button>
        </div>
      </ha-card>
    `;

    this._setupEventListeners();
  }

  _setupEventListeners() {
    const throttle = this.shadowRoot.getElementById('throttle');
    const btnStop = this.shadowRoot.getElementById('btn-stop');
    const btnForward = this.shadowRoot.getElementById('btn-forward');
    const btnReverse = this.shadowRoot.getElementById('btn-reverse');
    const btnLights = this.shadowRoot.getElementById('btn-lights');
    const btnHorn = this.shadowRoot.getElementById('btn-horn');
    const btnBell = this.shadowRoot.getElementById('btn-bell');
    const btnDisconnect = this.shadowRoot.getElementById('btn-disconnect');

    // Throttle slider
    throttle.addEventListener('input', (e) => {
      this._setThrottle(parseInt(e.target.value));
    });

    // Stop button
    btnStop.addEventListener('click', () => {
      this._pressButton('stop');
      throttle.value = 0;
      this.shadowRoot.getElementById('speed-display').textContent = '0%';
    });

    // Direction buttons
    btnForward.addEventListener('click', () => this._pressButton('forward'));
    btnReverse.addEventListener('click', () => this._pressButton('reverse'));

    // Control buttons
    btnLights.addEventListener('click', () => this._toggleSwitch('lights'));
    btnHorn.addEventListener('click', () => this._pressButton('horn'));
    btnBell.addEventListener('click', () => this._pressButton('bell'));
    btnDisconnect.addEventListener('click', () => this._pressButton('disconnect'));
  }

  _setThrottle(value) {
    const entityId = `number.${this._getEntityId('throttle')}`;
    this._hass.callService('number', 'set_value', {
      entity_id: entityId,
      value: value
    });
    this.shadowRoot.getElementById('speed-display').textContent = `${value}%`;
  }

  _pressButton(action) {
    const entityId = `button.${this._getEntityId(action)}`;
    this._hass.callService('button', 'press', {
      entity_id: entityId
    });
  }

  _toggleSwitch(action) {
    const entityId = `switch.${this._getEntityId(action)}`;
    this._hass.callService('switch', 'toggle', {
      entity_id: entityId
    });
  }

  _updateCard() {
    if (!this._hass || !this._config) return;

    // Update connection status
    const connectionEntity = `binary_sensor.${this._getEntityId('connected')}`;
    const connectionState = this._hass.states[connectionEntity];
    const statusEl = this.shadowRoot.getElementById('status');
    
    if (connectionState) {
      const isConnected = connectionState.state === 'on';
      statusEl.textContent = isConnected ? 'Connected' : 'Disconnected';
      statusEl.className = `status ${isConnected ? 'connected' : 'disconnected'}`;
      
      // Disable controls if disconnected
      const card = this.shadowRoot.querySelector('.card');
      if (!isConnected) {
        card.classList.add('unavailable');
      } else {
        card.classList.remove('unavailable');
      }
    }

    // Update throttle value
    const throttleEntity = `number.${this._getEntityId('throttle')}`;
    const throttleState = this._hass.states[throttleEntity];
    if (throttleState) {
      const value = parseFloat(throttleState.state) || 0;
      this.shadowRoot.getElementById('throttle').value = value;
      this.shadowRoot.getElementById('speed-display').textContent = `${Math.round(value)}%`;
    }

    // Update lights button state
    const lightsEntity = `switch.${this._getEntityId('lights')}`;
    const lightsState = this._hass.states[lightsEntity];
    const lightsBtn = this.shadowRoot.getElementById('btn-lights');
    if (lightsState && lightsBtn) {
      if (lightsState.state === 'on') {
        lightsBtn.classList.add('active');
      } else {
        lightsBtn.classList.remove('active');
      }
    }
  }

  getCardSize() {
    return 5;
  }

  static getConfigElement() {
    return document.createElement('lionel-train-card-editor');
  }

  static getStubConfig() {
    return {
      entity: 'number.lionel_train_throttle',
      name: 'Lionel Train'
    };
  }
}

// Card Editor
class LionelTrainCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this._render();
  }

  _render() {
    this.innerHTML = `
      <style>
        .editor {
          padding: 16px;
        }
        .editor label {
          display: block;
          margin-bottom: 4px;
          font-weight: 500;
        }
        .editor input {
          width: 100%;
          padding: 8px;
          border: 1px solid #ccc;
          border-radius: 4px;
          margin-bottom: 16px;
          box-sizing: border-box;
        }
      </style>
      <div class="editor">
        <label>Throttle Entity (number.xxx_throttle)</label>
        <input type="text" id="entity" value="${this._config.entity || ''}">
        
        <label>Card Name</label>
        <input type="text" id="name" value="${this._config.name || ''}">
      </div>
    `;

    this.querySelector('#entity').addEventListener('change', (e) => {
      this._config = { ...this._config, entity: e.target.value };
      this._fireEvent();
    });

    this.querySelector('#name').addEventListener('change', (e) => {
      this._config = { ...this._config, name: e.target.value };
      this._fireEvent();
    });
  }

  _fireEvent() {
    const event = new CustomEvent('config-changed', {
      detail: { config: this._config },
      bubbles: true,
      composed: true
    });
    this.dispatchEvent(event);
  }
}

// Register the card
customElements.define('lionel-train-card', LionelTrainCard);
customElements.define('lionel-train-card-editor', LionelTrainCardEditor);

// Register with Home Assistant
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'lionel-train-card',
  name: 'Lionel Train Controller',
  description: 'A custom card for controlling Lionel LionChief trains',
  preview: true
});

console.info('%c LIONEL-TRAIN-CARD %c Loaded ', 
  'color: white; background: #f44336; font-weight: bold;',
  'color: #f44336; background: white; font-weight: bold;'
);
