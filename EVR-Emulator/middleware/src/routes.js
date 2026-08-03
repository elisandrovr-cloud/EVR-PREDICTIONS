'use strict';

const express = require('express');
const adb = require('./adb-service');
const vm = require('./vm-service');
const config = require('./config');
const pkg = require('../package.json');

const router = express.Router();

/** Envuelve un handler async para que los rechazos acaben en el handler de errores. */
const wrap = (fn) => (req, res, next) => Promise.resolve(fn(req, res, next)).catch(next);

/** Un fallo por dispositivo ausente es 503 (temporal), no 500. */
function statusFor(err) {
  return /adb no encontrado|dispositivo|device|offline|no se pudo leer/i.test(err.message) ? 503 : 500;
}

const fail = (res, err) => res.status(statusFor(err)).json({ error: err.message });

// -- Salud y dispositivos ---------------------------------------------------

// Salud del servicio + estado del toolchain.
router.get('/health', (req, res) => {
  res.json({
    ok: true,
    service: 'evr-middleware',
    version: pkg.version,
    uptimeSec: Math.round(process.uptime()),
    platform: process.platform,
    adbPath: config.adbPath,
    adbAvailable: adb.isAvailable(),
    defaultSerial: config.defaultSerial,
    streamFps: config.streamFps,
  });
});

// Lista de dispositivos/VMs conectados.
router.get(
  '/devices',
  wrap(async (req, res) => {
    try {
      res.json({ devices: await adb.listDevices() });
    } catch (err) {
      fail(res, err);
    }
  })
);

// Conectar a una VM por TCP/IP: { "endpoint": "127.0.0.1:4444" }
router.post(
  '/connect',
  wrap(async (req, res) => {
    const { endpoint } = req.body || {};
    if (!endpoint) return res.status(400).json({ error: 'falta "endpoint"' });
    if (!/^[\w.-]+:\d{1,5}$/.test(endpoint)) {
      return res.status(400).json({ error: 'endpoint invalido (host:puerto)' });
    }
    try {
      res.json({ ok: true, result: await adb.connect(endpoint) });
    } catch (err) {
      fail(res, err);
    }
  })
);

// Desconectar: { "endpoint"? } (sin endpoint desconecta todos los TCP/IP)
router.post(
  '/disconnect',
  wrap(async (req, res) => {
    try {
      res.json({ ok: true, result: await adb.disconnect((req.body || {}).endpoint) });
    } catch (err) {
      fail(res, err);
    }
  })
);

// Ejecutar un comando shell: { "serial"?, "command": "getprop ro.product.model" }
router.post(
  '/shell',
  wrap(async (req, res) => {
    const { serial, command } = req.body || {};
    if (!command) return res.status(400).json({ error: 'falta "command"' });
    try {
      res.json({ ok: true, output: await adb.shell(serial, command) });
    } catch (err) {
      fail(res, err);
    }
  })
);

// -- Inyeccion de entrada ---------------------------------------------------

router.post(
  '/input/tap',
  wrap(async (req, res) => {
    const { serial, x, y } = req.body || {};
    if (!Number.isFinite(Number(x)) || !Number.isFinite(Number(y))) {
      return res.status(400).json({ error: 'faltan "x"/"y" numericos' });
    }
    try {
      await adb.tap(serial, Number(x), Number(y));
      res.json({ ok: true });
    } catch (err) {
      fail(res, err);
    }
  })
);

router.post(
  '/input/swipe',
  wrap(async (req, res) => {
    const { serial, x1, y1, x2, y2, durationMs } = req.body || {};
    if ([x1, y1, x2, y2].some((v) => !Number.isFinite(Number(v)))) {
      return res.status(400).json({ error: 'faltan coordenadas numericas x1/y1/x2/y2' });
    }
    try {
      await adb.swipe(serial, Number(x1), Number(y1), Number(x2), Number(y2), Number(durationMs) || 200);
      res.json({ ok: true });
    } catch (err) {
      fail(res, err);
    }
  })
);

router.post(
  '/input/text',
  wrap(async (req, res) => {
    const { serial, value } = req.body || {};
    if (value == null || value === '') return res.status(400).json({ error: 'falta "value"' });
    try {
      await adb.text(serial, value);
      res.json({ ok: true });
    } catch (err) {
      fail(res, err);
    }
  })
);

router.post(
  '/input/key',
  wrap(async (req, res) => {
    const { serial, code } = req.body || {};
    if (code == null) return res.status(400).json({ error: 'falta "code"' });
    try {
      await adb.keyevent(serial, code);
      res.json({ ok: true });
    } catch (err) {
      if (/keycode invalido/.test(err.message)) return res.status(400).json({ error: err.message });
      fail(res, err);
    }
  })
);

// -- Apps -------------------------------------------------------------------

// Instalacion de APK (ruta local en el host): { "serial"?, "apkPath": "C:\\apps\\mi.apk" }
router.post(
  '/apps/install',
  wrap(async (req, res) => {
    const { serial, apkPath } = req.body || {};
    if (!apkPath) return res.status(400).json({ error: 'falta "apkPath"' });
    try {
      res.json(await adb.install(serial, apkPath));
    } catch (err) {
      if (/APK no encontrado/.test(err.message)) return res.status(400).json({ error: err.message });
      fail(res, err);
    }
  })
);

router.post(
  '/apps/uninstall',
  wrap(async (req, res) => {
    const { serial, package: name } = req.body || {};
    if (!name) return res.status(400).json({ error: 'falta "package"' });
    try {
      res.json(await adb.uninstall(serial, name));
    } catch (err) {
      fail(res, err);
    }
  })
);

// Lanzar app por paquete o atajo: { "serial"?, "app": "tiktok" }
router.post(
  '/apps/launch',
  wrap(async (req, res) => {
    const { serial, app } = req.body || {};
    if (!app) return res.status(400).json({ error: 'falta "app" (paquete o atajo, p.ej. tiktok)' });
    try {
      res.json(await vm.launch(serial, app));
    } catch (err) {
      if (/paquete invalido/.test(err.message)) return res.status(400).json({ error: err.message });
      // La app no esta en el guest: es un 404, no un fallo del middleware.
      if (/esta instalado/.test(err.message)) return res.status(404).json({ error: err.message });
      fail(res, err);
    }
  })
);

// Abrir la ficha de Play Store: { "serial"?, "app": "tiktok" }
router.post(
  '/apps/play',
  wrap(async (req, res) => {
    const { serial, app } = req.body || {};
    if (!app) return res.status(400).json({ error: 'falta "app"' });
    try {
      res.json(await vm.openInPlayStore(serial, app));
    } catch (err) {
      if (/paquete invalido/.test(err.message)) return res.status(400).json({ error: err.message });
      fail(res, err);
    }
  })
);

// ¿Instalada?  GET /apps/installed?app=tiktok
router.get(
  '/apps/installed',
  wrap(async (req, res) => {
    const app = req.query.app;
    if (!app) return res.status(400).json({ error: 'falta "app"' });
    try {
      res.json(await vm.isInstalled(req.query.serial, app));
    } catch (err) {
      if (/paquete invalido/.test(err.message)) return res.status(400).json({ error: err.message });
      fail(res, err);
    }
  })
);

// Catalogo de atajos de app conocidos.
router.get('/apps/shortcuts', (req, res) => res.json({ shortcuts: vm.APP_SHORTCUTS }));

// -- Control de la VM -------------------------------------------------------

// Estado del emulador + props (modelo, version Android, marca).
router.get(
  '/vm/status',
  wrap(async (req, res) => {
    try {
      res.json(await vm.status(req.query.serial));
    } catch (err) {
      fail(res, err);
    }
  })
);

// "Formatear" el emulador: { "mode": "overlay" | "snapshot" | "fresh", "snapshot"?, "sizeGB"? }
// Requiere la VM apagada (lo valida vm-format).
router.post(
  '/vm/reset',
  wrap(async (req, res) => {
    try {
      res.json(await vm.reset(req.body || {}));
    } catch (err) {
      if (/modo desconocido|requiere|invalido|fuera de rango/.test(err.message)) {
        return res.status(400).json({ error: err.message });
      }
      fail(res, err);
    }
  })
);

// Captura de pantalla actual (image/png). Base para el control clic-para-tap.
router.get(
  '/screen',
  wrap(async (req, res) => {
    try {
      const png = await vm.screen(req.query.serial);
      res.set('Content-Type', 'image/png');
      res.set('Cache-Control', 'no-store');
      res.send(png);
    } catch (err) {
      res.status(503).json({ error: err.message });
    }
  })
);

// Resolucion del guest (para mapear coordenadas con exactitud).
router.get(
  '/screen/size',
  wrap(async (req, res) => {
    try {
      res.json(await adb.screenSize(req.query.serial));
    } catch (err) {
      res.status(503).json({ error: err.message });
    }
  })
);

// -- "Agent switcher": perfiles de dispositivo -----------------------------

// Catalogo de perfiles disponibles.
router.get('/vm/profiles', (req, res) => {
  try {
    res.json({ profiles: vm.listProfiles() });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Aplicar un perfil: { "serial"?, "id": "pixel7" }. Reinicia el guest.
router.post(
  '/vm/profile',
  wrap(async (req, res) => {
    const { serial, id } = req.body || {};
    if (!id) return res.status(400).json({ error: 'falta "id" del perfil' });
    try {
      res.json(await vm.applyProfile(serial, id));
    } catch (err) {
      if (/perfil desconocido/.test(err.message)) return res.status(404).json({ error: err.message });
      fail(res, err);
    }
  })
);

module.exports = router;
