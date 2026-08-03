'use strict';

const path = require('path');
const fs = require('fs');

// Carga .env de forma minima (sin dependencias) si existe.
(function loadDotEnv() {
  const envPath = path.resolve(__dirname, '..', '.env');
  if (!fs.existsSync(envPath)) return;
  const lines = fs.readFileSync(envPath, 'utf8').split(/\r?\n/);
  for (const line of lines) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/i);
    if (!m) continue;
    const key = m[1];
    let val = m[2];
    if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
      val = val.slice(1, -1);
    }
    if (process.env[key] === undefined) process.env[key] = val;
  }
})();

const projectRoot = path.resolve(__dirname, '..', '..');
const isWindows = process.platform === 'win32';
const exe = (name) => (isWindows ? `${name}.exe` : name);

/** Busca un ejecutable en el PATH del sistema (equivalente portable de `which`). */
function findInPath(name) {
  const dirs = (process.env.PATH || '').split(path.delimiter).filter(Boolean);
  const names = isWindows
    ? (process.env.PATHEXT || '.EXE;.CMD;.BAT').split(';').map((ext) => name + ext.toLowerCase())
    : [name];
  for (const dir of dirs) {
    for (const candidate of names) {
      const full = path.join(dir, candidate);
      try {
        if (fs.statSync(full).isFile()) return full;
      } catch (_) {
        /* no existe o el directorio del PATH es inaccesible: seguir buscando */
      }
    }
  }
  return null;
}

/**
 * Resuelve un binario por orden de prioridad:
 *   1. variable de entorno explicita,
 *   2. copia portable bajo bin/ (la que baja fetch-binaries),
 *   3. rutas conocidas del SDK de Android,
 *   4. PATH del sistema.
 * Si no aparece en ningun sitio devuelve la ruta portable, para que el mensaje
 * de error apunte a donde el usuario deberia instalarlo.
 */
function resolveBinary({ envVar, bundled, name, extra = [] }) {
  if (process.env[envVar]) return process.env[envVar];
  for (const candidate of [bundled, ...extra].filter(Boolean)) {
    if (fs.existsSync(candidate)) return candidate;
  }
  return findInPath(name) || bundled;
}

function androidSdkAdbCandidates() {
  const roots = [process.env.ANDROID_HOME, process.env.ANDROID_SDK_ROOT].filter(Boolean);
  const home = process.env.HOME || process.env.USERPROFILE;
  if (home) {
    roots.push(path.join(home, 'Android', 'Sdk'));
    roots.push(path.join(home, 'Library', 'Android', 'sdk')); // macOS
  }
  if (process.env.LOCALAPPDATA) roots.push(path.join(process.env.LOCALAPPDATA, 'Android', 'Sdk'));
  return roots.map((root) => path.join(root, 'platform-tools', exe('adb')));
}

function intEnv(name, fallback) {
  const parsed = parseInt(process.env[name] || '', 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

module.exports = {
  host: process.env.EVR_HOST || '127.0.0.1',
  port: intEnv('EVR_PORT', 5555),

  adbPath: resolveBinary({
    envVar: 'EVR_ADB_PATH',
    bundled: path.join(projectRoot, 'bin', 'platform-tools', exe('adb')),
    name: 'adb',
    extra: androidSdkAdbCandidates(),
  }),
  scrcpyPath: resolveBinary({
    envVar: 'EVR_SCRCPY_PATH',
    bundled: path.join(projectRoot, 'bin', 'scrcpy', exe('scrcpy')),
    name: 'scrcpy',
  }),

  // Interprete opcional con el que ejecutar EVR_ADB_PATH (p.ej. "node" para un
  // adb simulado). Vacio = se ejecuta el binario directamente.
  adbLauncher: process.env.EVR_ADB_LAUNCHER || null,

  // 'auto' usa adbkit (con la CLI como respaldo); 'cli' fuerza la CLI de adb.
  // Con un lanzador de por medio adbkit no sabe invocar el binario: solo CLI.
  adbMode: process.env.EVR_ADB_MODE === 'cli' || process.env.EVR_ADB_LAUNCHER ? 'cli' : 'auto',

  // Serial ADB del emulador (VM QEMU). Coincide con -HostAdbPort de launch-vm.
  defaultSerial: process.env.EVR_DEFAULT_SERIAL || '127.0.0.1:4444',
  // Reintento periodico de `adb connect` contra el serial por defecto (0 = off).
  autoConnectIntervalMs: intEnv('EVR_AUTOCONNECT_MS', 5000),

  // Streaming de pantalla (Fase 3): fotogramas por segundo objetivo.
  streamFps: clamp(intEnv('EVR_STREAM_FPS', 8), 1, 30),

  scriptsDir: path.join(projectRoot, 'scripts'),
  logLevel: process.env.EVR_LOG_LEVEL || 'info',
  isWindows,
  projectRoot,
};
