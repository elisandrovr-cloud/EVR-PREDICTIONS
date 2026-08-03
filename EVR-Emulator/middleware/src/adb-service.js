'use strict';

const fs = require('fs');
const { spawn } = require('child_process');
const { EventEmitter } = require('events');
const config = require('./config');
const log = require('./logger');

// adbkit es opcional en tiempo de carga: si aun no se ha corrido `npm install`,
// el servicio sigue funcionando via la CLI de adb (fallback robusto).
let Adb = null;
try {
  const mod = require('@devicefarmer/adbkit');
  Adb = mod.Adb || mod.default || mod;
} catch (err) {
  log.warn('adbkit no disponible todavia; usando fallback por CLI. Ejecuta `npm install`.');
}

const NO_ADB_MSG =
  'adb no encontrado en el host. Instalalo con scripts/fetch-binaries.ps1 (Windows), ' +
  'scripts/fetch-binaries.sh (Linux/macOS) o define EVR_ADB_PATH.';

// Estados que `adb devices` puede reportar en la segunda columna.
const DEVICE_STATES = new Set([
  'device',
  'offline',
  'unauthorized',
  'authorizing',
  'bootloader',
  'recovery',
  'sideload',
  'connecting',
  'host',
]);

/**
 * Entrecomilla un valor para el shell del guest. `adb shell` concatena los
 * argumentos y los reparsea /en el dispositivo/, asi que hay que citar aqui
 * aunque el proceso adb se lance sin shell en el host.
 */
function shellQuote(value) {
  return `'${String(value).replace(/'/g, `'\\''`)}'`;
}

/**
 * Texto para `input text`. Se envia entrecomillado (conserva espacios, acentos
 * y el caracter `%` literal, que sin comillas adb interpreta como escape).
 */
function escapeInputText(text) {
  return shellQuote(text);
}

/** Parsea la salida de `adb devices`, ignorando cabecera y mensajes del daemon. */
function parseDevices(raw) {
  return String(raw)
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => line.split(/\s+/))
    .filter((parts) => parts.length >= 2 && DEVICE_STATES.has(parts[1]))
    .map(([serial, type]) => ({ serial, type }));
}

class AdbService extends EventEmitter {
  constructor() {
    super();
    this.adbPath = config.adbPath;
    this.client = null;
    this.tracker = null;

    if (!this.isAvailable()) {
      log.warn(`adb no encontrado en ${this.adbPath}. ${NO_ADB_MSG}`);
    }
    if (Adb && config.adbMode !== 'cli') {
      this.client = Adb.createClient({ bin: this.adbPath });
    }
  }

  /** ¿Hay un binario adb utilizable en el host? */
  isAvailable() {
    try {
      return fs.statSync(this.adbPath).isFile();
    } catch (_) {
      return false;
    }
  }

  _requireAdb() {
    if (!this.isAvailable()) throw new Error(NO_ADB_MSG);
  }

  /**
   * Lanza adb. Con EVR_ADB_LAUNCHER definido, el binario se pasa como primer
   * argumento del interprete (util para apuntar a un adb simulado sin depender
   * del bit de ejecucion ni del shebang, que en Windows no existen).
   */
  _spawnAdb(args, opts = {}) {
    return config.adbLauncher
      ? spawn(config.adbLauncher, [this.adbPath, ...args], opts)
      : spawn(this.adbPath, args, opts);
  }

  // -- CLI directa (fallback / operaciones que no expone adbkit) --------------
  _cli(args, { timeoutMs = 15000 } = {}) {
    return new Promise((resolve, reject) => {
      let child;
      try {
        this._requireAdb();
        child = this._spawnAdb(args, { windowsHide: true });
      } catch (e) {
        return reject(e);
      }
      let out = '';
      let err = '';
      const timer = setTimeout(() => {
        child.kill('SIGKILL');
        reject(new Error(`adb ${args.join(' ')} agoto el tiempo de espera`));
      }, timeoutMs);

      child.stdout.on('data', (d) => (out += d));
      child.stderr.on('data', (d) => (err += d));
      child.on('error', (e) => {
        clearTimeout(timer);
        reject(e);
      });
      child.on('close', (code) => {
        clearTimeout(timer);
        if (code === 0) resolve(out.trim());
        else reject(new Error(err.trim() || out.trim() || `adb salio con codigo ${code}`));
      });
    });
  }

  _serialArgs(serial) {
    const s = serial || config.defaultSerial;
    return s ? ['-s', s] : [];
  }

  // -- Ciclo de vida ---------------------------------------------------------
  async start() {
    if (!this.isAvailable()) {
      log.warn('adb server no iniciado:', NO_ADB_MSG);
      return false;
    }
    await this._cli(['start-server']).catch((e) => log.warn('start-server:', e.message));
    log.info('adb server iniciado. adb =', this.adbPath);
    return true;
  }

  async listDevices() {
    // Sin binario adb (host de desarrollo, o antes de fetch-binaries): degradar
    // a lista vacia en vez de reventar con ENOENT.
    if (!this.isAvailable()) return [];
    if (this.client) {
      try {
        const devices = await this.client.listDevices();
        return devices.map((d) => ({ serial: d.id, type: d.type }));
      } catch (e) {
        log.debug('listDevices via adbkit fallo, usando CLI:', e.message);
      }
    }
    return parseDevices(await this._cli(['devices']));
  }

  /** Emite eventos 'add' / 'remove' / 'change' con { serial, type }. */
  async trackDevices() {
    if (!this.client || !this.isAvailable()) {
      log.warn('Seguimiento de dispositivos omitido (sin adbkit o sin adb).');
      return null;
    }
    try {
      this.tracker = await this.client.trackDevices();
    } catch (e) {
      log.warn('trackDevices:', e.message);
      return null;
    }
    this.tracker.on('add', (d) => this.emit('device', { event: 'add', serial: d.id, type: d.type }));
    this.tracker.on('remove', (d) => this.emit('device', { event: 'remove', serial: d.id, type: d.type }));
    this.tracker.on('change', (d) => this.emit('device', { event: 'change', serial: d.id, type: d.type }));
    this.tracker.on('error', (e) => log.error('tracker:', e.message));
    log.info('Seguimiento de dispositivos ADB activo.');
    return this.tracker;
  }

  stopTracking() {
    if (this.tracker && typeof this.tracker.end === 'function') {
      try {
        this.tracker.end();
      } catch (_) {
        /* ya cerrado */
      }
    }
    this.tracker = null;
  }

  // -- Shell -----------------------------------------------------------------
  async shell(serial, command) {
    this._requireAdb();
    if (this.client) {
      try {
        const dev = this.client.getDevice(serial || config.defaultSerial);
        const stream = await dev.shell(command);
        const buf = await Adb.util.readAll(stream);
        return buf.toString().trim();
      } catch (e) {
        log.debug('shell via adbkit fallo, usando CLI:', e.message);
      }
    }
    return this._cli([...this._serialArgs(serial), 'shell', command]);
  }

  // -- Inyeccion de eventos de entrada --------------------------------------
  async tap(serial, x, y) {
    return this.shell(serial, `input tap ${Math.round(x)} ${Math.round(y)}`);
  }

  async swipe(serial, x1, y1, x2, y2, durationMs = 200) {
    return this.shell(
      serial,
      `input swipe ${Math.round(x1)} ${Math.round(y1)} ${Math.round(x2)} ${Math.round(y2)} ${Math.round(durationMs)}`
    );
  }

  async text(serial, value) {
    return this.shell(serial, `input text ${escapeInputText(value)}`);
  }

  async keyevent(serial, code) {
    // code puede ser numerico (66) o simbolico (KEYCODE_ENTER)
    if (!/^(\d+|KEYCODE_[A-Z0-9_]+)$/.test(String(code))) {
      throw new Error(`keycode invalido: ${code}`);
    }
    return this.shell(serial, `input keyevent ${code}`);
  }

  /** Resolucion del guest, p.ej. { width: 1080, height: 1920 }. */
  async screenSize(serial) {
    const raw = await this.shell(serial, 'wm size');
    const m = raw.match(/(?:Override|Physical) size:\s*(\d+)x(\d+)/);
    if (!m) throw new Error(`no se pudo leer la resolucion: ${raw}`);
    return { width: parseInt(m[1], 10), height: parseInt(m[2], 10) };
  }

  // -- Gestion de APKs -------------------------------------------------------
  async install(serial, apkPath, { reinstall = true } = {}) {
    if (!fs.existsSync(apkPath)) throw new Error(`APK no encontrado: ${apkPath}`);
    this._requireAdb();
    if (this.client) {
      try {
        const dev = this.client.getDevice(serial || config.defaultSerial);
        await dev.install(apkPath); // adbkit maneja push + pm install
        return { ok: true, apk: apkPath };
      } catch (e) {
        log.debug('install via adbkit fallo, usando CLI:', e.message);
      }
    }
    const args = [...this._serialArgs(serial), 'install'];
    if (reinstall) args.push('-r');
    args.push(apkPath);
    const out = await this._cli(args, { timeoutMs: 300000 });
    return { ok: /Success/i.test(out), output: out };
  }

  async uninstall(serial, packageName) {
    this._requireAdb();
    if (this.client) {
      try {
        const dev = this.client.getDevice(serial || config.defaultSerial);
        await dev.uninstall(packageName);
        return { ok: true, package: packageName };
      } catch (e) {
        log.debug('uninstall via adbkit fallo, usando CLI:', e.message);
      }
    }
    const out = await this._cli([...this._serialArgs(serial), 'uninstall', packageName]);
    return { ok: /Success/i.test(out), output: out };
  }

  /** Conecta a una VM Android por TCP/IP (p.ej. 127.0.0.1:4444). */
  async connect(endpoint) {
    const out = await this._cli(['connect', endpoint]);
    if (/unable to connect|failed to connect|cannot connect/i.test(out)) {
      throw new Error(out);
    }
    return out;
  }

  async disconnect(endpoint) {
    return this._cli(endpoint ? ['disconnect', endpoint] : ['disconnect']);
  }

  // -- Operaciones de bajo nivel (para perfiles de dispositivo) --------------
  async root(serial) {
    return this._cli([...this._serialArgs(serial), 'root']).catch((e) => e.message);
  }

  async remount(serial) {
    return this._cli([...this._serialArgs(serial), 'remount']).catch((e) => e.message);
  }

  async pull(serial, remote, local) {
    return this._cli([...this._serialArgs(serial), 'pull', remote, local], { timeoutMs: 30000 });
  }

  async push(serial, local, remote) {
    return this._cli([...this._serialArgs(serial), 'push', local, remote], { timeoutMs: 30000 });
  }

  async reboot(serial) {
    return this._cli([...this._serialArgs(serial), 'reboot']).catch((e) => e.message);
  }

  /** Captura de pantalla PNG (Buffer) via `screencap`. */
  screencap(serial, { timeoutMs = 15000 } = {}) {
    return new Promise((resolve, reject) => {
      if (!this.isAvailable()) return reject(new Error(NO_ADB_MSG));
      const args = [...this._serialArgs(serial), 'exec-out', 'screencap', '-p'];
      const child = this._spawnAdb(args, { windowsHide: true });
      const chunks = [];
      let err = '';
      const timer = setTimeout(() => {
        child.kill('SIGKILL');
        reject(new Error('screencap agoto el tiempo de espera'));
      }, timeoutMs);
      child.stdout.on('data', (d) => chunks.push(d));
      child.stderr.on('data', (d) => (err += d));
      child.on('error', (e) => {
        clearTimeout(timer);
        reject(e);
      });
      child.on('close', (code) => {
        clearTimeout(timer);
        const buf = Buffer.concat(chunks);
        // adb devuelve 0 aunque el dispositivo no exista: validar la firma PNG.
        const isPng = buf.length > 8 && buf.readUInt32BE(0) === 0x89504e47;
        if (code === 0 && isPng) resolve(buf);
        else reject(new Error(err.trim() || 'screencap sin datos (¿dispositivo conectado?)'));
      });
    });
  }
}

module.exports = new AdbService();
module.exports.escapeInputText = escapeInputText;
module.exports.shellQuote = shellQuote;
module.exports.parseDevices = parseDevices;
module.exports.AdbService = AdbService;
