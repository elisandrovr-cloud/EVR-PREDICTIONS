'use strict';

/**
 * Enrutado de handshakes WebSocket por ruta.
 *
 * `ws` aborta el socket cuando un WebSocketServer con la opcion `server` recibe
 * un upgrade de una ruta que no es la suya, asi que no se pueden montar dos
 * canales (/ws y /ws/video) de esa forma. Aqui cada canal se crea con
 * `noServer: true` y este modulo despacha el upgrade al que corresponda.
 */

const HANDLED = Symbol('evr.upgradeHandled');

function pathOf(req) {
  try {
    return new URL(req.url, 'http://localhost').pathname;
  } catch (_) {
    return null;
  }
}

/** Encamina los upgrades de `pathname` hacia `wss`. Devuelve el "des-registrador". */
function routeUpgrade(server, pathname, wss) {
  const onUpgrade = (req, socket, head) => {
    if (req[HANDLED] || pathOf(req) !== pathname) return;
    req[HANDLED] = true;
    wss.handleUpgrade(req, socket, head, (ws) => wss.emit('connection', ws, req));
  };
  server.on('upgrade', onUpgrade);
  return () => server.off('upgrade', onUpgrade);
}

/**
 * Cierra los upgrades que nadie reclamo. Debe registrarse DESPUES de todos los
 * canales para que se ejecute el ultimo.
 */
function attachUpgradeFallback(server) {
  const onUpgrade = (req, socket) => {
    if (req[HANDLED]) return;
    socket.write('HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n');
    socket.destroy();
  };
  server.on('upgrade', onUpgrade);
  return () => server.off('upgrade', onUpgrade);
}

module.exports = { routeUpgrade, attachUpgradeFallback, HANDLED };
