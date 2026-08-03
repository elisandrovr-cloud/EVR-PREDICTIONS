'use strict';

const path = require('path');
const fs = require('fs');
const os = require('os');
const { spawn } = require('child_process');
const config = require('./config');
const adb = require('./adb-service');
const log = require('./logger');

const PROFILES_PATH = path.join(config.projectRoot, 'config', 'device-profiles.json');

/**
 * Control de la VM Android desde el middleware:
 *  - reset()  : "formatea" el emulador (recrea el overlay) via vm-format.
 *  - status() : estado del dispositivo + props clave via ADB.
 *  - launch() : lanza una app por nombre de paquete.
 *
 * reset() exige que la VM (QEMU) este APAGADA; lo valida el propio script.
 * Se usa vm-format.ps1 en Windows y vm-format.sh en Linux/macOS.
 */

const APP_SHORTCUTS = {
  tiktok: 'com.zhiliaoapp.musically',
  'tiktok-lite': 'com.zhiliaoapp.musically.go',
  trill: 'com.ss.android.ugc.trill',
  play: 'com.android.vending',
  playstore: 'com.android.vending',
  chrome: 'com.android.chrome',
  settings: 'com.android.settings',
  youtube: 'com.google.android.youtube',
};

// Nombre de paquete Android valido: segmentos alfanumericos separados por puntos.
const PACKAGE_RE = /^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$/;

/** Lanza uno de los scripts del proyecto, eligiendo .ps1 o .sh segun el host. */
function runScript(baseName, args = [], { timeoutMs = 60000 } = {}) {
  return new Promise((resolve, reject) => {
    const script = path.join(config.scriptsDir, `${baseName}${config.isWindows ? '.ps1' : '.sh'}`);
    if (!fs.existsSync(script)) {
      return reject(new Error(`script no encontrado: ${script}`));
    }
    const [cmd, cmdArgs] = config.isWindows
      ? ['powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', script, ...args]]
      : ['/bin/sh', [script, ...args]];

    const child = spawn(cmd, cmdArgs, { windowsHide: true });
    let out = '';
    let err = '';
    const timer = setTimeout(() => {
      child.kill();
      reject(new Error(`${baseName} agoto el tiempo de espera`));
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
      else reject(new Error(err.trim() || out.trim() || `${baseName} salio con codigo ${code}`));
    });
  });
}

/**
 * "Formatea" el emulador. Los scripts .ps1 y .sh aceptan los mismos modificadores
 * (-Force / -Snapshot <n> / -Fresh / -SizeGB <n>).
 */
async function reset({ mode = 'overlay', snapshot, sizeGB } = {}) {
  const args = ['-Force'];
  if (mode === 'snapshot') {
    if (!snapshot) throw new Error('mode=snapshot requiere "snapshot"');
    if (!/^[\w.-]{1,64}$/.test(snapshot)) throw new Error('nombre de snapshot invalido');
    args.push('-Snapshot', snapshot);
  } else if (mode === 'fresh') {
    args.push('-Fresh');
    if (sizeGB) {
      const gb = parseInt(sizeGB, 10);
      if (!Number.isFinite(gb) || gb < 1 || gb > 1024) throw new Error('sizeGB fuera de rango (1-1024)');
      args.push('-SizeGB', String(gb));
    }
  } else if (mode !== 'overlay') {
    throw new Error(`modo desconocido: ${mode} (overlay | snapshot | fresh)`);
  }
  const output = await runScript('vm-format', args, { timeoutMs: 120000 });
  return { ok: true, mode, output };
}

/** Estado del emulador + propiedades relevantes. */
async function status(serial) {
  const s = serial || config.defaultSerial;
  const devices = await adb.listDevices();
  const online = devices.some((d) => d.serial === s && d.type === 'device');
  let props = {};
  let screen = null;
  if (online) {
    try {
      const raw = await adb.shell(
        s,
        'getprop ro.product.model; getprop ro.build.version.release; getprop ro.product.brand'
      );
      const [model, release, brand] = raw.split(/\r?\n/).map((x) => x.trim());
      props = { model, androidRelease: release, brand };
      screen = await adb.screenSize(s).catch(() => null);
    } catch (e) {
      log.debug('status props:', e.message);
    }
  }
  return {
    serial: s,
    online,
    devices,
    props,
    screen,
    adb: { path: config.adbPath, available: adb.isAvailable() },
    platform: process.platform,
  };
}

/** Resuelve un atajo (tiktok, play...) o valida un nombre de paquete explicito. */
function resolvePackage(appOrPackage) {
  const key = String(appOrPackage || '').trim().toLowerCase();
  const pkg = APP_SHORTCUTS[key] || String(appOrPackage || '').trim();
  if (!PACKAGE_RE.test(pkg)) throw new Error(`nombre de paquete invalido: ${appOrPackage}`);
  return pkg;
}

/** Lanza una app por paquete (o atajo tiktok/play/chrome...). */
async function launch(serial, appOrPackage) {
  const pkg = resolvePackage(appOrPackage);
  const out = await adb.shell(serial, `monkey -p ${pkg} -c android.intent.category.LAUNCHER 1`);
  if (/No activities found|Error:/i.test(out)) {
    throw new Error(`no se pudo lanzar ${pkg}: ¿esta instalado?`);
  }
  return { ok: true, package: pkg, output: out };
}

/** Abre la ficha de Play Store de un paquete dentro del guest. */
async function openInPlayStore(serial, appOrPackage) {
  const pkg = resolvePackage(appOrPackage);
  await adb.shell(serial, `am start -a android.intent.action.VIEW -d market://details?id=${pkg}`);
  return { ok: true, package: pkg };
}

/** ¿Esta instalado el paquete en el guest? */
async function isInstalled(serial, appOrPackage) {
  const pkg = resolvePackage(appOrPackage);
  const out = await adb.shell(serial, `pm list packages ${pkg}`);
  return { package: pkg, installed: out.split(/\r?\n/).some((l) => l.trim() === `package:${pkg}`) };
}

// -- "Agent switcher": perfiles de dispositivo -----------------------------

function listProfiles() {
  if (!fs.existsSync(PROFILES_PATH)) {
    throw new Error(`no se encontro config/device-profiles.json en ${PROFILES_PATH}`);
  }
  let raw;
  try {
    raw = JSON.parse(fs.readFileSync(PROFILES_PATH, 'utf8'));
  } catch (e) {
    throw new Error(`device-profiles.json invalido: ${e.message}`);
  }
  if (!raw || !Array.isArray(raw.profiles)) throw new Error('device-profiles.json: falta el array "profiles"');
  return raw.profiles.map((p) => ({ id: p.id, label: p.label, props: p.props }));
}

/**
 * Aplica un perfil de dispositivo: reescribe las props en /system/build.prop
 * del guest y reinicia. Presenta la VM como un modelo Android estandar (privacidad
 * + compatibilidad). Requiere root/remount en el guest (BlissOS lo soporta).
 * No es un bypass de attestation: solo edita cadenas de identificacion de modelo.
 */
async function applyProfile(serial, id) {
  const profile = listProfiles().find((p) => p.id === id);
  if (!profile) throw new Error(`perfil desconocido: ${id}`);
  const s = serial || config.defaultSerial;

  await adb.root(s);
  await adb.remount(s);

  const tmp = path.join(os.tmpdir(), `evr-build-${Date.now()}.prop`);
  try {
    await adb.pull(s, '/system/build.prop', tmp);
    let content = fs.readFileSync(tmp, 'utf8');

    for (const [key, value] of Object.entries(profile.props)) {
      const line = `${key}=${value}`;
      const re = new RegExp(`^${key.replace(/\./g, '\\.')}=.*$`, 'm');
      content = re.test(content) ? content.replace(re, line) : `${content}\n${line}`;
    }
    fs.writeFileSync(tmp, content);
    await adb.push(s, tmp, '/system/build.prop');
  } finally {
    fs.rmSync(tmp, { force: true });
  }
  await adb.reboot(s);

  return {
    ok: true,
    profile: profile.id,
    label: profile.label,
    note: 'reiniciando el guest para aplicar el perfil',
  };
}

/** Captura de pantalla actual del guest (Buffer PNG). */
function screen(serial) {
  return adb.screencap(serial || config.defaultSerial);
}

module.exports = {
  reset,
  status,
  launch,
  openInPlayStore,
  isInstalled,
  listProfiles,
  applyProfile,
  screen,
  resolvePackage,
  runScript,
  APP_SHORTCUTS,
  // alias historico
  TIKTOK_PACKAGES: APP_SHORTCUTS,
};
