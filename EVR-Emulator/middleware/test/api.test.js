'use strict';

const path = require('path');
const os = require('os');
const fs = require('fs');

const LOG = path.join(os.tmpdir(), `evr-adb-log-${process.pid}.txt`);
process.env.EVR_ADB_LAUNCHER = process.execPath;
process.env.EVR_ADB_PATH = path.join(__dirname, '..', 'test-helpers', 'fake-adb.js');
process.env.EVR_FAKE_ADB_LOG = LOG;
process.env.EVR_DEFAULT_SERIAL = '127.0.0.1:4444';
process.env.EVR_LOG_LEVEL = 'error';

const test = require('node:test');
const assert = require('node:assert');
const { createServer } = require('../server');

let server;
let base;

test.before(async () => {
  fs.writeFileSync(LOG, '');
  server = createServer();
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  base = `http://127.0.0.1:${server.address().port}`;
});

test.after(() => {
  server.close();
  fs.rmSync(LOG, { force: true });
});

const get = (p) => fetch(base + p);
const post = (p, body) =>
  fetch(base + p, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
const adbLog = () => fs.readFileSync(LOG, 'utf8');

test('GET /api/health informa del estado del toolchain', async () => {
  const res = await get('/api/health');
  assert.strictEqual(res.status, 200);
  const body = await res.json();
  assert.strictEqual(body.ok, true);
  assert.strictEqual(body.service, 'evr-middleware');
  assert.strictEqual(body.adbAvailable, true);
  assert.ok(body.streamFps >= 1);
});

test('GET /api/devices lista el dispositivo conectado', async () => {
  const body = await (await get('/api/devices')).json();
  assert.deepStrictEqual(body.devices, [{ serial: '127.0.0.1:4444', type: 'device' }]);
});

test('GET /api/vm/status resuelve props y resolucion del guest', async () => {
  const body = await (await get('/api/vm/status')).json();
  assert.strictEqual(body.online, true);
  assert.strictEqual(body.props.model, 'EVR Test');
  assert.strictEqual(body.props.androidRelease, '13');
  assert.deepStrictEqual(body.screen, { width: 1080, height: 1920 });
  assert.strictEqual(body.adb.available, true);
});

test('POST /api/input/tap inyecta el toque en el dispositivo', async () => {
  const res = await post('/api/input/tap', { x: 10.4, y: 20.6 });
  assert.strictEqual(res.status, 200);
  assert.match(adbLog(), /shell input tap 10 21/);
});

test('POST /api/input/tap sin coordenadas responde 400', async () => {
  const res = await post('/api/input/tap', { x: 10 });
  assert.strictEqual(res.status, 400);
  assert.match((await res.json()).error, /x.*y/);
});

test('POST /api/input/swipe traslada el gesto con su duracion', async () => {
  const res = await post('/api/input/swipe', { x1: 1, y1: 2, x2: 3, y2: 4, durationMs: 250 });
  assert.strictEqual(res.status, 200);
  assert.match(adbLog(), /shell input swipe 1 2 3 4 250/);
});

test('POST /api/input/text preserva espacios y acentos', async () => {
  const res = await post('/api/input/text', { value: "mi contraseña 'segura'" });
  assert.strictEqual(res.status, 200);
  assert.match(adbLog(), /input text 'mi contraseña/);
});

test('POST /api/input/key rechaza un keycode inventado', async () => {
  const res = await post('/api/input/key', { code: 'KEYCODE_HOME; reboot' });
  assert.strictEqual(res.status, 400);
});

test('POST /api/apps/launch acepta el atajo tiktok', async () => {
  const res = await post('/api/apps/launch', { app: 'tiktok' });
  assert.strictEqual(res.status, 200);
  const body = await res.json();
  assert.strictEqual(body.package, 'com.zhiliaoapp.musically');
});

test('POST /api/apps/launch avisa si la app no esta instalada', async () => {
  const res = await post('/api/apps/launch', { app: 'com.no.instalada' });
  assert.strictEqual(res.status, 404);
  assert.match((await res.json()).error, /instalado/);
});

test('POST /api/apps/launch rechaza un paquete con inyeccion', async () => {
  const res = await post('/api/apps/launch', { app: 'com.x; rm -rf /' });
  assert.strictEqual(res.status, 400);
});

test('GET /api/apps/installed consulta el gestor de paquetes', async () => {
  const body = await (await get('/api/apps/installed?app=tiktok')).json();
  assert.deepStrictEqual(body, { package: 'com.zhiliaoapp.musically', installed: true });
});

test('GET /api/screen devuelve un PNG del guest', async () => {
  const res = await get('/api/screen');
  assert.strictEqual(res.status, 200);
  assert.strictEqual(res.headers.get('content-type'), 'image/png');
  const buf = Buffer.from(await res.arrayBuffer());
  assert.strictEqual(buf.readUInt32BE(0), 0x89504e47, 'firma PNG');
});

test('GET /api/screen responde 503 si el guest no da imagen', async () => {
  process.env.EVR_FAKE_ADB_FAIL = 'screencap';
  try {
    const res = await get('/api/screen');
    assert.strictEqual(res.status, 503);
    assert.match((await res.json()).error, /offline|screencap/i);
  } finally {
    delete process.env.EVR_FAKE_ADB_FAIL;
  }
});

test('GET /api/vm/profiles expone el catalogo del agent switcher', async () => {
  const body = await (await get('/api/vm/profiles')).json();
  assert.ok(body.profiles.some((p) => p.id === 'pixel7'));
});

test('POST /api/vm/profile con un perfil inexistente responde 404', async () => {
  const res = await post('/api/vm/profile', { id: 'nokia3310' });
  assert.strictEqual(res.status, 404);
});

test('POST /api/vm/reset valida el modo antes de tocar el disco', async () => {
  const res = await post('/api/vm/reset', { mode: 'destruirlo-todo' });
  assert.strictEqual(res.status, 400);
});

test('POST /api/connect valida el endpoint', async () => {
  assert.strictEqual((await post('/api/connect', { endpoint: 'no-es-un-endpoint' })).status, 400);
  const ok = await post('/api/connect', { endpoint: '127.0.0.1:4444' });
  assert.strictEqual(ok.status, 200);
});

test('la consola web se sirve en la raiz', async () => {
  const res = await get('/');
  assert.strictEqual(res.status, 200);
  const html = await res.text();
  assert.match(html, /Elisandro/);
  assert.match(html, /id="screen"/);
});
