'use strict';

// EVR Emulator - frontend "Elisandro".
// Cliente del middleware: REST (/api), control (/ws) y video (/ws/video).

const el = (id) => document.getElementById(id);
const wsUrl = (path) =>
  `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}${path}`;

// ---------------------------------------------------------------------------
// Log
// ---------------------------------------------------------------------------
const MAX_LOG_LINES = 300;

function log(msg, kind = '') {
  const box = el('log');
  const line = document.createElement('div');
  const time = document.createElement('span');
  time.className = 't';
  time.textContent = new Date().toLocaleTimeString();
  const body = document.createElement('span');
  body.className = kind;
  body.textContent = ` ${msg}`;
  line.append(time, body);
  box.appendChild(line);
  while (box.childElementCount > MAX_LOG_LINES) box.removeChild(box.firstChild);
  box.scrollTop = box.scrollHeight;
}

// ---------------------------------------------------------------------------
// REST
// ---------------------------------------------------------------------------
async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...opts });
  const ct = res.headers.get('content-type') || '';
  const body = ct.includes('application/json') ? await res.json() : await res.text();
  if (!res.ok) throw new Error((body && body.error) || res.statusText);
  return body;
}
const post = (path, data) => api(path, { method: 'POST', body: JSON.stringify(data || {}) });

// ---------------------------------------------------------------------------
// Canal de video (/ws/video): el servidor empuja los fotogramas.
// Si el WebSocket no esta disponible se cae a sondeo HTTP de /api/screen.
// ---------------------------------------------------------------------------
class ScreenView {
  constructor(canvas, overlay) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.overlay = overlay;
    this.ws = null;
    this.size = null; // resolucion real del guest
    this.paused = false;
    this.fps = 8;
    this.frames = 0;
    this.fpsShown = 0;
    this.pollTimer = null;
    this.retries = 0;
    setInterval(() => {
      this.fpsShown = this.frames;
      this.frames = 0;
      const label = el('fpsMeter');
      if (label) label.textContent = this.live ? `${this.fpsShown} fps` : '';
    }, 1000);
  }

  get live() {
    return !!(this.ws && this.ws.readyState === WebSocket.OPEN);
  }

  connect() {
    if (!('WebSocket' in window)) return this.startPolling();
    let ws;
    try {
      ws = new WebSocket(wsUrl('/ws/video'));
    } catch (e) {
      return this.startPolling();
    }
    ws.binaryType = 'blob';
    this.ws = ws;

    ws.onopen = () => {
      this.retries = 0;
      this.stopPolling();
      this.setFps(this.fps);
      log('video en directo conectado', 'ok');
    };
    ws.onmessage = (ev) => {
      if (typeof ev.data === 'string') return this.onControl(ev.data);
      this.draw(ev.data);
    };
    ws.onclose = () => {
      this.ws = null;
      this.retries += 1;
      // Reintento con espera creciente; mientras tanto, sondeo HTTP.
      if (this.retries >= 2) this.startPolling();
      setTimeout(() => this.connect(), Math.min(10000, 1000 * this.retries));
    };
    ws.onerror = () => {};
  }

  onControl(raw) {
    let msg;
    try {
      msg = JSON.parse(raw);
    } catch (_) {
      return;
    }
    if (msg.type === 'size') {
      this.size = { width: msg.width, height: msg.height };
      this.canvas.width = msg.width;
      this.canvas.height = msg.height;
    } else if (msg.type === 'stream') {
      this.fps = msg.fps;
      log(`stream ${msg.serial} a ${msg.fps} fps`, 'ok');
    } else if (msg.type === 'offline') {
      this.showOverlay(true);
    } else if (msg.type === 'online') {
      log('dispositivo en linea', 'ok');
    }
  }

  async draw(blob) {
    try {
      const bitmap = await createImageBitmap(blob);
      if (this.canvas.width !== bitmap.width || this.canvas.height !== bitmap.height) {
        this.canvas.width = bitmap.width;
        this.canvas.height = bitmap.height;
      }
      this.size = { width: bitmap.width, height: bitmap.height };
      this.ctx.drawImage(bitmap, 0, 0);
      bitmap.close();
      this.frames += 1;
      this.showOverlay(false);
    } catch (e) {
      /* fotograma corrupto: se ignora, llegara el siguiente */
    }
  }

  showOverlay(on) {
    this.overlay.style.display = on ? 'flex' : 'none';
    this.canvas.style.display = on ? 'none' : 'block';
  }

  setFps(fps) {
    this.fps = fps;
    if (this.live) this.ws.send(JSON.stringify({ type: 'fps', value: fps }));
    if (this.pollTimer) this.startPolling(); // reajusta el sondeo
  }

  setPaused(paused) {
    this.paused = paused;
    if (this.live) this.ws.send(JSON.stringify({ type: paused ? 'pause' : 'resume' }));
    if (paused) this.stopPolling();
    else if (!this.live) this.startPolling();
  }

  // -- Respaldo por HTTP ----------------------------------------------------
  startPolling() {
    this.stopPolling();
    if (this.paused) return;
    const tick = async () => {
      try {
        const res = await fetch(`/api/screen?ts=${Date.now()}`);
        if (!res.ok) throw new Error('sin pantalla');
        await this.draw(await res.blob());
      } catch (e) {
        this.showOverlay(true);
      }
    };
    tick();
    this.pollTimer = setInterval(tick, Math.round(1000 / Math.min(this.fps, 4)));
  }

  stopPolling() {
    clearInterval(this.pollTimer);
    this.pollTimer = null;
  }

  /**
   * Convierte coordenadas del navegador a pixeles del guest.
   * El canvas usa `object-fit: contain`, asi que la imagen va centrada y con
   * bandas a los lados cuando su proporcion no coincide con la del marco:
   * hay que descontarlas o el toque cae desplazado.
   */
  toDevice(clientX, clientY) {
    const rect = this.canvas.getBoundingClientRect();
    if (!rect.width || !rect.height || !this.size) return null;
    const scale = Math.min(rect.width / this.size.width, rect.height / this.size.height);
    const shownW = this.size.width * scale;
    const shownH = this.size.height * scale;
    const x = (clientX - (rect.left + (rect.width - shownW) / 2)) / scale;
    const y = (clientY - (rect.top + (rect.height - shownH) / 2)) / scale;
    if (x < 0 || y < 0 || x > this.size.width || y > this.size.height) return null; // banda lateral
    return { x: Math.round(x), y: Math.round(y) };
  }
}

// ---------------------------------------------------------------------------
// Estado del dispositivo
// ---------------------------------------------------------------------------
let deviceOnline = false;

async function refreshStatus() {
  try {
    const st = await api('/api/vm/status');
    deviceOnline = st.online;
    el('statusDot').className = 'dot ' + (st.online ? 'on' : 'off');
    el('statusText').textContent = st.online ? `conectado · ${st.serial}` : 'sin dispositivo';
    el('deviceModel').textContent = st.props && st.props.model ? st.props.model : '';
    el('connState').textContent = st.online ? 'en vivo' : 'buscando dispositivo…';
    if (!st.adb || !st.adb.available) {
      el('connState').textContent = 'adb no instalado en el host';
    }
    return st.online;
  } catch (e) {
    deviceOnline = false;
    el('statusDot').className = 'dot off';
    el('statusText').textContent = 'middleware no responde';
    el('connState').textContent = 'middleware no responde';
    return false;
  }
}

// ---------------------------------------------------------------------------
// WebSocket de control (/ws): eventos de dispositivo
// ---------------------------------------------------------------------------
function connectControlWs() {
  let ws;
  try {
    ws = new WebSocket(wsUrl('/ws'));
  } catch (e) {
    return;
  }
  ws.onopen = () => log('control conectado', 'ok');
  ws.onclose = () => setTimeout(connectControlWs, 3000);
  ws.onerror = () => {};
  ws.onmessage = (m) => {
    let msg;
    try {
      msg = JSON.parse(m.data);
    } catch (_) {
      return;
    }
    if (msg.type === 'device') {
      log(`dispositivo ${msg.event}: ${msg.serial}`);
      refreshStatus();
    } else if (msg.type === 'welcome') {
      log(`middleware ${msg.server} v${msg.version}`, 'ok');
    } else if (msg.type === 'error') {
      log('control: ' + msg.message, 'err');
    }
  };
}

// ---------------------------------------------------------------------------
// Entrada: clic = toque, arrastrar = deslizar, teclado = texto/teclas
// ---------------------------------------------------------------------------
const SWIPE_THRESHOLD_PX = 12; // por debajo de esto es un toque, no un swipe

function bindInput(view) {
  const canvas = view.canvas;
  let down = null;

  canvas.addEventListener('pointerdown', (ev) => {
    const p = view.toDevice(ev.clientX, ev.clientY);
    if (!p) return;
    down = { ...p, t: Date.now(), clientX: ev.clientX, clientY: ev.clientY };
    canvas.setPointerCapture(ev.pointerId);
  });

  canvas.addEventListener('pointerup', async (ev) => {
    if (!down) return;
    const start = down;
    down = null;
    const end = view.toDevice(ev.clientX, ev.clientY);
    if (!end) return;
    const dist = Math.hypot(ev.clientX - start.clientX, ev.clientY - start.clientY);
    try {
      if (dist < SWIPE_THRESHOLD_PX) {
        await post('/api/input/tap', { x: end.x, y: end.y });
        log(`tap ${end.x},${end.y}`, 'ok');
      } else {
        const durationMs = Math.min(1000, Math.max(80, Date.now() - start.t));
        await post('/api/input/swipe', { x1: start.x, y1: start.y, x2: end.x, y2: end.y, durationMs });
        log(`swipe ${start.x},${start.y} → ${end.x},${end.y}`, 'ok');
      }
    } catch (e) {
      log('entrada: ' + e.message, 'err');
    }
  });

  canvas.addEventListener('pointercancel', () => (down = null));
  canvas.addEventListener('contextmenu', (ev) => ev.preventDefault());

  // Rueda del raton = deslizamiento vertical.
  let wheelAcc = 0;
  let wheelTimer = null;
  canvas.addEventListener(
    'wheel',
    (ev) => {
      ev.preventDefault();
      if (!view.size) return;
      wheelAcc += ev.deltaY;
      clearTimeout(wheelTimer);
      wheelTimer = setTimeout(async () => {
        const amount = Math.max(-600, Math.min(600, wheelAcc));
        wheelAcc = 0;
        const cx = Math.round(view.size.width / 2);
        const cy = Math.round(view.size.height / 2);
        try {
          await post('/api/input/swipe', {
            x1: cx,
            y1: cy,
            x2: cx,
            y2: Math.round(cy - amount),
            durationMs: 150,
          });
        } catch (e) {
          log('scroll: ' + e.message, 'err');
        }
      }, 60);
    },
    { passive: false }
  );

  // Teclado fisico cuando el marco tiene el foco.
  const KEYMAP = {
    Enter: 'KEYCODE_ENTER',
    Backspace: 'KEYCODE_DEL',
    Escape: 'KEYCODE_BACK',
    Tab: 'KEYCODE_TAB',
    ArrowUp: 'KEYCODE_DPAD_UP',
    ArrowDown: 'KEYCODE_DPAD_DOWN',
    ArrowLeft: 'KEYCODE_DPAD_LEFT',
    ArrowRight: 'KEYCODE_DPAD_RIGHT',
  };
  canvas.setAttribute('tabindex', '0');
  canvas.addEventListener('keydown', async (ev) => {
    if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
    try {
      if (KEYMAP[ev.key]) {
        ev.preventDefault();
        await post('/api/input/key', { code: KEYMAP[ev.key] });
      } else if (ev.key.length === 1) {
        ev.preventDefault();
        await post('/api/input/text', { value: ev.key });
      }
    } catch (e) {
      log('tecla: ' + e.message, 'err');
    }
  });
}

// ---------------------------------------------------------------------------
// Agent switcher (perfiles de dispositivo)
// ---------------------------------------------------------------------------
let profiles = [];

async function loadProfiles() {
  try {
    const r = await api('/api/vm/profiles');
    profiles = r.profiles;
    const sel = el('profileSelect');
    sel.innerHTML = '';
    profiles.forEach((p) => {
      const o = document.createElement('option');
      o.value = p.id;
      o.textContent = p.label;
      sel.appendChild(o);
    });
    showProfileProps();
    log(`${profiles.length} perfiles de dispositivo cargados`, 'ok');
  } catch (e) {
    log('perfiles: ' + e.message, 'err');
  }
}

function showProfileProps() {
  const p = profiles.find((x) => x.id === el('profileSelect').value);
  el('profileProps').textContent = p
    ? Object.entries(p.props)
        .map(([k, v]) => `${k}=${v}`)
        .join('\n')
    : '';
}

// ---------------------------------------------------------------------------
// Bindings de la interfaz
// ---------------------------------------------------------------------------
function bindUi(view) {
  el('autoRefresh').onchange = (e) => view.setPaused(!e.target.checked);
  el('refreshRate').onchange = (e) => view.setFps(parseInt(e.target.value, 10));
  el('frameType').onchange = (e) => {
    el('deviceFrame').className = 'device-frame ' + e.target.value;
  };

  document.querySelectorAll('.nav, #btnEnter').forEach((b) => {
    b.onclick = async () => {
      try {
        await post('/api/input/key', { code: b.dataset.key });
        log('key ' + b.dataset.key, 'ok');
      } catch (e) {
        log('key: ' + e.message, 'err');
      }
    };
  });

  const sendText = async () => {
    const value = el('textInput').value;
    if (!value) return;
    try {
      await post('/api/input/text', { value });
      log('texto enviado', 'ok');
      el('textInput').value = '';
    } catch (e) {
      log('texto: ' + e.message, 'err');
    }
  };
  el('btnText').onclick = sendText;
  el('textInput').onkeydown = (ev) => {
    if (ev.key === 'Enter') sendText();
  };

  el('btnTikTok').onclick = async () => {
    try {
      const r = await post('/api/apps/launch', { app: 'tiktok' });
      log('lanzando ' + r.package, 'ok');
    } catch (e) {
      log('TikTok: ' + e.message, 'err');
    }
  };
  el('btnPlayTikTok').onclick = async () => {
    try {
      await post('/api/apps/play', { app: 'tiktok' });
      log('abriendo Play Store', 'ok');
    } catch (e) {
      log('Play: ' + e.message, 'err');
    }
  };
  el('btnLaunchPkg').onclick = async () => {
    const app = el('pkgInput').value.trim();
    if (!app) return;
    try {
      const r = await post('/api/apps/launch', { app });
      log('lanzando ' + r.package, 'ok');
    } catch (e) {
      log('launch: ' + e.message, 'err');
    }
  };
  el('btnInstallApk').onclick = async () => {
    const apkPath = el('apkInput').value.trim();
    if (!apkPath) return;
    log('instalando ' + apkPath + '…');
    try {
      const r = await post('/api/apps/install', { apkPath });
      log('install: ' + (r.ok ? 'OK' : JSON.stringify(r)), r.ok ? 'ok' : 'err');
    } catch (e) {
      log('install: ' + e.message, 'err');
    }
  };

  el('profileSelect').onchange = showProfileProps;
  el('btnApplyProfile').onclick = async () => {
    const id = el('profileSelect').value;
    if (!confirm(`¿Aplicar el perfil "${id}" y reiniciar el guest?`)) return;
    try {
      const r = await post('/api/vm/profile', { id });
      log('perfil aplicado: ' + r.label, 'ok');
    } catch (e) {
      log('perfil: ' + e.message, 'err');
    }
  };

  el('btnStatus').onclick = refreshStatus;
  el('btnFormat').onclick = async () => {
    const mode = el('resetMode').value;
    if (!confirm(`¿Formatear el emulador (${mode})? La VM debe estar apagada.`)) return;
    try {
      const r = await post('/api/vm/reset', { mode });
      log('formateo: ' + (r.ok ? 'OK' : 'fallo'), r.ok ? 'ok' : 'err');
    } catch (e) {
      log('formateo: ' + e.message, 'err');
    }
  };
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
(async function init() {
  const view = new ScreenView(el('screen'), el('screenOverlay'));
  bindUi(view);
  bindInput(view);
  connectControlWs();
  view.setFps(parseInt(el('refreshRate').value, 10));
  view.connect();
  await loadProfiles();
  await refreshStatus();
  setInterval(refreshStatus, 4000);
  log('consola lista · el middleware busca el dispositivo solo', 'ok');
})();
