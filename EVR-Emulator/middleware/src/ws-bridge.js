'use strict';

const { WebSocketServer } = require('ws');
const adb = require('./adb-service');
const vm = require('./vm-service');
const log = require('./logger');
const pkg = require('../package.json');
const { routeUpgrade } = require('./ws-upgrade');

/**
 * Puente WebSocket de control (canal /ws).
 *
 * Protocolo (JSON por mensaje):
 *   Cliente -> servidor:
 *     { "type": "tap",    "serial"?, "x": <n>, "y": <n> }
 *     { "type": "swipe",  "serial"?, "x1", "y1", "x2", "y2", "durationMs"? }
 *     { "type": "text",   "serial"?, "value": "<str>" }
 *     { "type": "key",    "serial"?, "code": <n|"KEYCODE_..."> }
 *     { "type": "shell",  "serial"?, "command": "<str>" }
 *     { "type": "launch", "serial"?, "app": "tiktok" }
 *     { "type": "status", "serial"? }
 *     { "type": "devices" }
 *     { "type": "ping" }
 *
 *   Servidor -> cliente:
 *     { "type": "welcome", "server": "evr-middleware", "version": "..." }
 *     { "type": "ack",     "for": "<type>", "id"?, "result"? }
 *     { "type": "error",   "for": "<type>", "id"?, "message": "<str>" }
 *     { "type": "device",  "event": "add|remove|change", "serial", "type" }
 *     { "type": "pong" }
 *
 * El canal de video va aparte, en /ws/video (ver video-bridge.js).
 */
function attachWsBridge(server) {
  const wss = new WebSocketServer({ noServer: true });
  const unroute = routeUpgrade(server, '/ws', wss);

  const broadcast = (evt) => {
    const payload = JSON.stringify({ type: 'device', ...evt });
    for (const client of wss.clients) {
      if (client.readyState === client.OPEN) client.send(payload);
    }
  };
  // Reenvia los eventos de dispositivo de ADB a todos los clientes conectados.
  adb.on('device', broadcast);

  wss.on('connection', (ws, req) => {
    const peer = req.socket.remoteAddress;
    log.info(`WS conectado desde ${peer}`);
    ws.isAlive = true;
    ws.on('pong', () => (ws.isAlive = true));

    ws.send(JSON.stringify({ type: 'welcome', server: 'evr-middleware', version: pkg.version }));

    ws.on('message', async (data) => {
      let msg;
      try {
        msg = JSON.parse(data.toString());
      } catch (e) {
        return ws.send(JSON.stringify({ type: 'error', for: null, message: 'JSON invalido' }));
      }

      const reply = (obj) => {
        if (ws.readyState === ws.OPEN) ws.send(JSON.stringify(msg.id ? { id: msg.id, ...obj } : obj));
      };
      const s = msg.serial;

      try {
        switch (msg.type) {
          case 'ping':
            return reply({ type: 'pong' });
          case 'devices':
            return reply({ type: 'ack', for: 'devices', result: await adb.listDevices() });
          case 'status':
            return reply({ type: 'ack', for: 'status', result: await vm.status(s) });
          case 'tap':
            await adb.tap(s, msg.x, msg.y);
            return reply({ type: 'ack', for: 'tap' });
          case 'swipe':
            await adb.swipe(s, msg.x1, msg.y1, msg.x2, msg.y2, msg.durationMs);
            return reply({ type: 'ack', for: 'swipe' });
          case 'text':
            await adb.text(s, msg.value);
            return reply({ type: 'ack', for: 'text' });
          case 'key':
            await adb.keyevent(s, msg.code);
            return reply({ type: 'ack', for: 'key' });
          case 'shell':
            return reply({ type: 'ack', for: 'shell', result: await adb.shell(s, msg.command) });
          case 'launch':
            return reply({ type: 'ack', for: 'launch', result: await vm.launch(s, msg.app) });
          default:
            return reply({ type: 'error', for: msg.type || null, message: 'tipo no soportado' });
        }
      } catch (err) {
        log.error(`WS ${msg.type}:`, err.message);
        return reply({ type: 'error', for: msg.type, message: err.message });
      }
    });

    ws.on('close', () => log.info(`WS desconectado (${peer})`));
    ws.on('error', (e) => log.warn('WS error:', e.message));
  });

  // Heartbeat: descarta conexiones muertas cada 30s.
  const heartbeat = setInterval(() => {
    for (const ws of wss.clients) {
      if (ws.isAlive === false) {
        ws.terminate();
        continue;
      }
      ws.isAlive = false;
      ws.ping();
    }
  }, 30000);
  heartbeat.unref();

  wss.closeBridge = () => {
    clearInterval(heartbeat);
    unroute();
    adb.off('device', broadcast);
    for (const client of wss.clients) client.terminate();
    wss.close();
  };

  log.info('Puente WebSocket montado en /ws');
  return wss;
}

module.exports = { attachWsBridge };
