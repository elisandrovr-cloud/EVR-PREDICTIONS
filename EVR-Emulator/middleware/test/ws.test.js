'use strict';

const path = require('path');

process.env.EVR_ADB_LAUNCHER = process.execPath;
process.env.EVR_ADB_PATH = path.join(__dirname, '..', 'test-helpers', 'fake-adb.js');
process.env.EVR_DEFAULT_SERIAL = '127.0.0.1:4444';
process.env.EVR_LOG_LEVEL = 'error';
process.env.EVR_STREAM_FPS = '20';

const test = require('node:test');
const assert = require('node:assert');
const WebSocket = require('ws');
const { createServer } = require('../server');

let server;
let port;

test.before(async () => {
  server = createServer();
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  port = server.address().port;
});

test.after(() => server.close());

/**
 * Abre un WebSocket y lo cierra al terminar el bloque.
 *
 * El buzon se engancha antes del 'open': el servidor manda el saludo (y el
 * primer fotograma) nada mas aceptar la conexion, y si se escuchara despues
 * esos mensajes se perderian.
 */
async function withSocket(pathname, fn) {
  const ws = new WebSocket(`ws://127.0.0.1:${port}${pathname}`);
  const inbox = [];
  const waiters = [];
  ws.on('message', (data, isBinary) => {
    const entry = { msg: isBinary ? data : JSON.parse(data.toString()), isBinary };
    inbox.push(entry);
    for (const waiter of waiters.splice(0)) waiter(entry);
  });
  ws.inbox = inbox;
  ws.waiters = waiters;

  await new Promise((resolve, reject) => {
    ws.once('open', resolve);
    ws.once('error', reject);
  });
  try {
    return await fn(ws);
  } finally {
    ws.close();
  }
}

/** Primer mensaje (ya recibido o futuro) que cumpla el predicado. */
function waitFor(ws, predicate, { timeoutMs = 4000 } = {}) {
  const hit = ws.inbox.find((e) => predicate(e.msg, e.isBinary));
  if (hit) return Promise.resolve(hit.msg);

  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      const idx = ws.waiters.indexOf(onEntry);
      if (idx >= 0) ws.waiters.splice(idx, 1);
      reject(new Error('tiempo agotado esperando el mensaje'));
    }, timeoutMs);
    function onEntry(entry) {
      if (predicate(entry.msg, entry.isBinary)) {
        clearTimeout(timer);
        resolve(entry.msg);
      } else {
        ws.waiters.push(onEntry);
      }
    }
    ws.waiters.push(onEntry);
  });
}

// -- Canal de control -------------------------------------------------------

test('/ws saluda al conectar', async () => {
  await withSocket('/ws', async (ws) => {
    const msg = await waitFor(ws, (m) => m.type === 'welcome');
    assert.strictEqual(msg.server, 'evr-middleware');
    assert.ok(msg.version);
  });
});

test('/ws responde al ping', async () => {
  await withSocket('/ws', async (ws) => {
    ws.send(JSON.stringify({ type: 'ping' }));
    assert.strictEqual((await waitFor(ws, (m) => m.type === 'pong')).type, 'pong');
  });
});

test('/ws devuelve la lista de dispositivos', async () => {
  await withSocket('/ws', async (ws) => {
    ws.send(JSON.stringify({ type: 'devices' }));
    const msg = await waitFor(ws, (m) => m.for === 'devices');
    assert.deepStrictEqual(msg.result, [{ serial: '127.0.0.1:4444', type: 'device' }]);
  });
});

test('/ws inyecta un toque y confirma', async () => {
  await withSocket('/ws', async (ws) => {
    ws.send(JSON.stringify({ type: 'tap', x: 5, y: 7 }));
    assert.strictEqual((await waitFor(ws, (m) => m.for === 'tap')).type, 'ack');
  });
});

test('/ws correlaciona la respuesta con el id de la peticion', async () => {
  await withSocket('/ws', async (ws) => {
    ws.send(JSON.stringify({ id: 'abc123', type: 'ping' }));
    const msg = await waitFor(ws, (m) => m.id === 'abc123');
    assert.strictEqual(msg.type, 'pong');
  });
});

test('/ws rechaza JSON invalido sin caerse', async () => {
  await withSocket('/ws', async (ws) => {
    ws.send('{esto no es json');
    const msg = await waitFor(ws, (m) => m.type === 'error');
    assert.match(msg.message, /JSON invalido/);
  });
});

test('/ws informa de un tipo desconocido', async () => {
  await withSocket('/ws', async (ws) => {
    ws.send(JSON.stringify({ type: 'autodestruccion' }));
    const msg = await waitFor(ws, (m) => m.type === 'error');
    assert.match(msg.message, /no soportado/);
  });
});

// -- Canal de video ---------------------------------------------------------

test('/ws/video anuncia el stream y empuja fotogramas PNG', async () => {
  await withSocket('/ws/video', async (ws) => {
    const hello = await waitFor(ws, (m) => !Buffer.isBuffer(m) && m.type === 'stream');
    assert.strictEqual(hello.format, 'image/png');
    assert.strictEqual(hello.serial, '127.0.0.1:4444');

    const frame = await waitFor(ws, (m, isBinary) => isBinary);
    assert.ok(Buffer.isBuffer(frame));
    assert.strictEqual(frame.readUInt32BE(0), 0x89504e47, 'el fotograma es un PNG');
  });
});

test('/ws/video comunica la resolucion del guest', async () => {
  await withSocket('/ws/video', async (ws) => {
    const size = await waitFor(ws, (m, isBinary) => !isBinary && m.type === 'size');
    assert.deepStrictEqual({ w: size.width, h: size.height }, { w: 270, h: 480 });
  });
});

test('/ws/video acepta cambiar los fps en caliente', async () => {
  await withSocket('/ws/video', async (ws) => {
    await waitFor(ws, (m, isBinary) => !isBinary && m.type === 'stream');
    ws.send(JSON.stringify({ type: 'fps', value: 3 }));
    const msg = await waitFor(ws, (m, isBinary) => !isBinary && m.type === 'stream' && m.fps === 3);
    assert.strictEqual(msg.fps, 3);
  });
});

test('/ws/video deja de enviar fotogramas en pausa', async () => {
  await withSocket('/ws/video', async (ws) => {
    await waitFor(ws, (m, isBinary) => isBinary);
    ws.send(JSON.stringify({ type: 'pause' }));
    await new Promise((r) => setTimeout(r, 120)); // deja pasar los que ya iban en vuelo

    let frames = 0;
    ws.on('message', (_d, isBinary) => {
      if (isBinary) frames += 1;
    });
    await new Promise((r) => setTimeout(r, 400));
    assert.strictEqual(frames, 0, 'en pausa no llegan fotogramas');
  });
});

test('/ws/video avisa cuando el guest deja de responder', async () => {
  process.env.EVR_FAKE_ADB_FAIL = 'screencap';
  try {
    await withSocket('/ws/video', async (ws) => {
      const msg = await waitFor(ws, (m, isBinary) => !isBinary && m.type === 'offline');
      assert.ok(msg.message);
    });
  } finally {
    delete process.env.EVR_FAKE_ADB_FAIL;
  }
});

test('una ruta WebSocket desconocida se rechaza', async () => {
  const ws = new WebSocket(`ws://127.0.0.1:${port}/ws/inventado`);
  const err = await new Promise((resolve) => {
    ws.once('error', resolve);
    ws.once('open', () => resolve(null));
  });
  ws.close();
  assert.ok(err, 'el handshake no deberia completarse');
});

test('el bucle de captura se detiene al irse el ultimo cliente', async () => {
  const hub = server.listeners('upgrade').length; // sanity: hay canales montados
  assert.ok(hub >= 2);

  await withSocket('/ws/video', async (ws) => {
    await waitFor(ws, (m, isBinary) => isBinary);
  });
  await new Promise((r) => setTimeout(r, 150));
  // Sin suscriptores el hub libera el stream; una nueva conexion lo recrea.
  await withSocket('/ws/video', async (ws) => {
    await waitFor(ws, (m, isBinary) => isBinary);
  });
});
