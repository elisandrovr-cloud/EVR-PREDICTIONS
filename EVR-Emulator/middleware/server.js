'use strict';

/**
 * EVR Emulator - Middleware (Capa 3).
 * Servidor local que expone API REST + WebSocket en localhost:<EVR_PORT>
 * y actua como puente ADB hacia la VM Android del entorno Elisandro.
 */

const http = require('http');
const path = require('path');
const express = require('express');

const config = require('./src/config');
const log = require('./src/logger');
const adb = require('./src/adb-service');
const routes = require('./src/routes');
const { attachWsBridge } = require('./src/ws-bridge');
const { attachVideoBridge } = require('./src/video-bridge');
const { attachUpgradeFallback } = require('./src/ws-upgrade');

/** Construye la app Express (sin escuchar): reutilizable desde las pruebas. */
function createApp() {
  const app = express();
  app.use(express.json({ limit: '1mb' }));

  // CORS abierto solo para el frontend local (Capa 4).
  app.use((req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS');
    res.header('Access-Control-Allow-Headers', 'Content-Type');
    if (req.method === 'OPTIONS') return res.sendStatus(204);
    next();
  });

  app.use('/api', routes);

  // Sirve el frontend "Elisandro" (Capa 4).
  app.use('/', express.static(path.join(config.projectRoot, 'frontend')));

  // Handler de errores.
  app.use((err, req, res, next) => { // eslint-disable-line no-unused-vars
    log.error('HTTP:', err.message);
    if (res.headersSent) return;
    res.status(500).json({ error: err.message });
  });

  return app;
}

/**
 * Crea el servidor HTTP con los dos canales WebSocket montados.
 * No arranca la escucha ni toca ADB: eso lo hace start().
 */
function createServer() {
  const server = http.createServer(createApp());
  const control = attachWsBridge(server);
  const video = attachVideoBridge(server);
  // Debe ir despues de los canales: cierra los upgrades a rutas desconocidas.
  attachUpgradeFallback(server);
  server.on('close', () => {
    control.closeBridge();
    video.closeBridge();
  });
  return server;
}

/**
 * Reintenta `adb connect` contra el serial por defecto hasta que enganche.
 * Asi la consola encuentra la VM sola en cuanto QEMU levanta el guest.
 */
function startAutoConnect() {
  const { defaultSerial, autoConnectIntervalMs } = config;
  if (!defaultSerial || !autoConnectIntervalMs || !defaultSerial.includes(':')) return null;

  let connected = false;
  const tick = async () => {
    try {
      const devices = await adb.listDevices();
      const online = devices.some((d) => d.serial === defaultSerial && d.type === 'device');
      if (online) {
        if (!connected) log.info(`Dispositivo ${defaultSerial} en linea.`);
        connected = true;
        return;
      }
      connected = false;
      await adb.connect(defaultSerial);
      log.info(`Conectado a ${defaultSerial}.`);
    } catch (err) {
      log.debug('auto-connect:', err.message);
    }
  };
  tick();
  const timer = setInterval(tick, autoConnectIntervalMs);
  timer.unref();
  return timer;
}

async function start() {
  const server = createServer();

  // Arranca ADB y el seguimiento de dispositivos (best-effort: sin adb el
  // servidor sigue en pie y la consola muestra "sin dispositivo").
  try {
    if (await adb.start()) {
      await adb.trackDevices();
    }
  } catch (err) {
    log.warn('Inicializacion ADB parcial:', err.message);
  }
  const autoConnect = startAutoConnect();

  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(config.port, config.host, resolve);
  });

  log.info('====================================================');
  log.info(` EVR middleware escuchando en http://${config.host}:${config.port}`);
  log.info(`  Consola : http://${config.host}:${config.port}`);
  log.info(`  REST    : http://${config.host}:${config.port}/api/health`);
  log.info(`  WS      : ws://${config.host}:${config.port}/ws`);
  log.info(`  Video   : ws://${config.host}:${config.port}/ws/video`);
  log.info(`  adb     : ${config.adbPath}${adb.isAvailable() ? '' : '  (NO ENCONTRADO)'}`);
  log.info('====================================================');

  // Apagado ordenado.
  let closing = false;
  const shutdown = (sig) => {
    if (closing) return;
    closing = true;
    log.info(`Recibido ${sig}, cerrando...`);
    if (autoConnect) clearInterval(autoConnect);
    adb.stopTracking();
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(0), 3000).unref();
  };
  process.on('SIGINT', () => shutdown('SIGINT'));
  process.on('SIGTERM', () => shutdown('SIGTERM'));

  return server;
}

if (require.main === module) {
  start().catch((err) => {
    log.error('Fallo fatal al arrancar:', err.message);
    process.exit(1);
  });
}

module.exports = { createApp, createServer, start, startAutoConnect };
