'use strict';

const { WebSocketServer } = require('ws');
const config = require('./config');
const log = require('./logger');
const { StreamHub } = require('./screen-stream');
const { routeUpgrade } = require('./ws-upgrade');

/**
 * Canal de video (Fase 3): /ws/video
 *
 * El servidor empuja los fotogramas del guest en cuanto cambian, en lugar de
 * que el navegador los pida uno a uno por HTTP. Menos latencia, menos peticiones
 * y ancho de banda cercano a cero con la pantalla quieta.
 *
 *   Servidor -> cliente:
 *     texto  { "type": "stream", "serial", "fps", "format": "image/png" }
 *     texto  { "type": "size",    "width", "height" }     (al cambiar la resolucion)
 *     texto  { "type": "offline", "message" }             (sin dispositivo)
 *     texto  { "type": "online" }                         (dispositivo recuperado)
 *     binario  <PNG>                                      (fotograma)
 *
 *   Cliente -> servidor:
 *     { "type": "fps",    "value": 8 }
 *     { "type": "pause" } | { "type": "resume" }
 *
 * El transporte es binario y agnostico al codec: cuando scrcpy entregue H265,
 * solo cambia el productor de fotogramas (screen-stream.js), no el protocolo.
 */

// Si el socket acumula mas de esto sin drenar, se saltan fotogramas.
const MAX_BUFFERED_BYTES = 4 * 1024 * 1024;

function attachVideoBridge(server, { hub = new StreamHub() } = {}) {
  const wss = new WebSocketServer({ noServer: true });
  const unroute = routeUpgrade(server, '/ws/video', wss);

  wss.on('connection', (ws, req) => {
    let serial;
    try {
      serial = new URL(req.url, 'http://localhost').searchParams.get('serial') || config.defaultSerial;
    } catch (_) {
      serial = config.defaultSerial;
    }

    const stream = hub.get(serial);
    let paused = false;
    let dropped = 0;

    const sendJson = (obj) => {
      if (ws.readyState === ws.OPEN) ws.send(JSON.stringify(obj));
    };

    const onFrame = (png) => {
      if (paused || ws.readyState !== ws.OPEN) return;
      // Backpressure: con la red congestionada es mejor perder fotogramas que
      // acumular retraso (el ultimo fotograma es el unico que importa).
      if (ws.bufferedAmount > MAX_BUFFERED_BYTES) {
        dropped += 1;
        return;
      }
      ws.send(png, { binary: true });
    };
    const onResize = (size) => sendJson({ type: 'size', ...size });
    const onOffline = (message) => sendJson({ type: 'offline', message });
    const onOnline = () => sendJson({ type: 'online' });

    stream.on('frame', onFrame);
    stream.on('resize', onResize);
    stream.on('offline', onOffline);
    stream.on('online', onOnline);
    stream.subscribe();

    sendJson({ type: 'stream', serial, fps: stream.fps, format: 'image/png' });
    if (stream.lastSize) sendJson({ type: 'size', ...stream.lastSize });
    log.info(`Video WS conectado (${serial}), suscriptores=${stream.subscribers}`);

    ws.on('message', (data) => {
      let msg;
      try {
        msg = JSON.parse(data.toString());
      } catch (_) {
        return;
      }
      if (msg.type === 'fps') {
        const fps = stream.setFps(msg.value);
        sendJson({ type: 'stream', serial, fps, format: 'image/png' });
      } else if (msg.type === 'pause') {
        paused = true;
      } else if (msg.type === 'resume') {
        paused = false;
        stream.lastHash = null; // reenvia el fotograma actual aunque no haya cambiado
      }
    });

    const cleanup = () => {
      stream.off('frame', onFrame);
      stream.off('resize', onResize);
      stream.off('offline', onOffline);
      stream.off('online', onOnline);
      stream.unsubscribe();
      hub.release(serial);
      if (dropped) log.debug(`Video WS ${serial}: ${dropped} fotogramas descartados por congestion`);
      log.info(`Video WS desconectado (${serial})`);
    };
    ws.on('close', cleanup);
    ws.on('error', (e) => {
      log.warn('Video WS error:', e.message);
      cleanup();
    });
  });

  wss.closeBridge = () => {
    unroute();
    for (const client of wss.clients) client.terminate();
    hub.stopAll();
    wss.close();
  };
  wss.hub = hub;

  log.info('Canal de video montado en /ws/video');
  return wss;
}

module.exports = { attachVideoBridge, MAX_BUFFERED_BYTES };
