#!/usr/bin/env node
'use strict';

/**
 * `npm run doctor` - diagnostico del entorno del middleware.
 * Responde a "¿por que no veo la pantalla del Android?" sin tener que leer logs.
 */

const fs = require('fs');
const net = require('net');
const path = require('path');
const config = require('../src/config');
const adb = require('../src/adb-service');
const vm = require('../src/vm-service');

let failures = 0;
let warnings = 0;

const line = (tag, label, detail) => console.log(`${tag} ${label.padEnd(34)} ${detail || ''}`);
const ok = (l, d) => line('[  OK  ]', l, d);
const warn = (l, d) => {
  warnings += 1;
  line('[ WARN ]', l, d);
};
const fail = (l, d) => {
  failures += 1;
  line('[ FAIL ]', l, d);
};
const info = (l, d) => line('[ INFO ]', l, d);

function portFree(port, host) {
  return new Promise((resolve) => {
    const srv = net
      .createServer()
      .once('error', () => resolve(false))
      .once('listening', () => srv.close(() => resolve(true)))
      .listen(port, host);
  });
}

async function main() {
  console.log('\n=== EVR Emulator · diagnostico del middleware ===\n');

  info('Plataforma', `${process.platform} · Node ${process.version}`);
  const major = parseInt(process.versions.node.split('.')[0], 10);
  if (major >= 18) ok('Version de Node.js', `>= 18 (${process.version})`);
  else fail('Version de Node.js', `${process.version}: se requiere >= 18`);

  // Dependencias
  if (fs.existsSync(path.join(__dirname, '..', 'node_modules'))) ok('Dependencias npm', 'instaladas');
  else fail('Dependencias npm', 'faltan: ejecuta `npm install`');

  // Configuracion
  const envPath = path.join(__dirname, '..', '.env');
  if (fs.existsSync(envPath)) ok('.env', envPath);
  else warn('.env', 'no existe (se usan valores por defecto); copia .env.example');

  info('Escucha', `${config.host}:${config.port}`);
  if (await portFree(config.port, config.host)) ok('Puerto libre', `${config.port} disponible`);
  else warn('Puerto ocupado', `${config.port} en uso (¿ya hay un middleware corriendo?)`);

  // ADB
  if (adb.isAvailable()) {
    ok('adb', config.adbPath);
    try {
      const devices = await adb.listDevices();
      if (devices.length) {
        ok('Dispositivos', devices.map((d) => `${d.serial} (${d.type})`).join(', '));
      } else {
        warn('Dispositivos', 'ninguno conectado: arranca la VM o conecta un telefono/AVD');
      }
      const target = devices.find((d) => d.serial === config.defaultSerial && d.type === 'device');
      if (target) {
        const size = await adb.screenSize(config.defaultSerial).catch(() => null);
        if (size) ok('Pantalla del guest', `${size.width}x${size.height}`);
        else warn('Pantalla del guest', 'no se pudo leer `wm size`');
      } else {
        info('Serial por defecto', `${config.defaultSerial} (aun sin conectar)`);
      }
    } catch (err) {
      fail('adb devices', err.message);
    }
  } else {
    fail('adb', `no encontrado (${config.adbPath})`);
    info('Solucion', 'scripts/fetch-binaries.(ps1|sh) o define EVR_ADB_PATH');
  }

  // Perfiles de dispositivo
  try {
    const profiles = vm.listProfiles();
    ok('Perfiles de dispositivo', `${profiles.length}: ${profiles.map((p) => p.id).join(', ')}`);
  } catch (err) {
    fail('config/device-profiles.json', err.message);
  }

  // Frontend
  const indexHtml = path.join(config.projectRoot, 'frontend', 'index.html');
  if (fs.existsSync(indexHtml)) ok('Consola web', indexHtml);
  else fail('Consola web', `no se encontro ${indexHtml}`);

  // Scripts de VM del host actual
  const vmScript = path.join(config.scriptsDir, `vm-format${config.isWindows ? '.ps1' : '.sh'}`);
  if (fs.existsSync(vmScript)) ok('Script de formateo', vmScript);
  else warn('Script de formateo', `no existe ${vmScript}`);

  console.log(`\nFallos: ${failures}   Advertencias: ${warnings}\n`);
  process.exit(failures > 0 ? 1 : 0);
}

main().catch((err) => {
  console.error('doctor:', err.message);
  process.exit(1);
});
