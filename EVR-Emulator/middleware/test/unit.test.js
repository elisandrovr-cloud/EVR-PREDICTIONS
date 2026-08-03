'use strict';

process.env.EVR_ADB_LAUNCHER = process.execPath;
process.env.EVR_ADB_PATH = require('path').join(__dirname, '..', 'test-helpers', 'fake-adb.js');

const test = require('node:test');
const assert = require('node:assert');

const adb = require('../src/adb-service');
const vm = require('../src/vm-service');
const { ScreenStream, StreamHub, pngSize } = require('../src/screen-stream');
const { makePng } = require('../test-helpers/png');

test('parseDevices ignora cabecera y mensajes del daemon', () => {
  const raw = [
    '* daemon not running; starting now at tcp:5037',
    '* daemon started successfully',
    'List of devices attached',
    '127.0.0.1:4444\tdevice',
    'emulator-5554\toffline',
    '',
  ].join('\n');
  assert.deepStrictEqual(adb.parseDevices(raw), [
    { serial: '127.0.0.1:4444', type: 'device' },
    { serial: 'emulator-5554', type: 'offline' },
  ]);
});

test('parseDevices con cero dispositivos devuelve lista vacia', () => {
  assert.deepStrictEqual(adb.parseDevices('List of devices attached\n\n'), []);
});

test('el texto se entrecomilla para el shell del guest', () => {
  assert.strictEqual(adb.escapeInputText('hola mundo'), `'hola mundo'`);
  // El `%` sobrevive: sin comillas `input text` lo tomaria como escape.
  assert.strictEqual(adb.escapeInputText('100%s'), `'100%s'`);
  // Comilla simple: se cierra, se escapa y se reabre (sin romper el comando).
  assert.strictEqual(adb.escapeInputText("it's"), `'it'\\''s'`);
});

test('shellQuote neutraliza intentos de inyeccion', () => {
  const quoted = adb.shellQuote('a; rm -rf /');
  assert.strictEqual(quoted, `'a; rm -rf /'`);
  assert.ok(!/^[^']*;/.test(quoted), 'el punto y coma queda dentro de las comillas');
});

test('keyevent rechaza codigos que no son keycodes', async () => {
  await assert.rejects(() => adb.keyevent(null, 'KEYCODE_HOME; reboot'), /keycode invalido/);
  await assert.rejects(() => adb.keyevent(null, '$(whoami)'), /keycode invalido/);
});

test('resolvePackage acepta atajos y paquetes, rechaza basura', () => {
  assert.strictEqual(vm.resolvePackage('tiktok'), 'com.zhiliaoapp.musically');
  assert.strictEqual(vm.resolvePackage('TikTok'), 'com.zhiliaoapp.musically');
  assert.strictEqual(vm.resolvePackage('com.ejemplo.app'), 'com.ejemplo.app');
  assert.throws(() => vm.resolvePackage('sin-puntos'), /invalido/);
  assert.throws(() => vm.resolvePackage('com.a; rm -rf /'), /invalido/);
});

test('los perfiles de dispositivo del catalogo son validos', () => {
  const profiles = vm.listProfiles();
  assert.ok(profiles.length >= 4);
  for (const p of profiles) {
    assert.ok(p.id && p.label, 'cada perfil tiene id y etiqueta');
    assert.ok(p.props['ro.product.model'], `${p.id} define ro.product.model`);
    assert.ok(p.props['ro.build.fingerprint'], `${p.id} define ro.build.fingerprint`);
  }
  assert.strictEqual(new Set(profiles.map((p) => p.id)).size, profiles.length, 'ids unicos');
});

test('reset valida el modo y los parametros antes de tocar el disco', async () => {
  await assert.rejects(() => vm.reset({ mode: 'raro' }), /modo desconocido/);
  await assert.rejects(() => vm.reset({ mode: 'snapshot' }), /requiere "snapshot"/);
  await assert.rejects(() => vm.reset({ mode: 'fresh', sizeGB: 99999 }), /fuera de rango/);
});

test('pngSize lee la resolucion de la cabecera IHDR', () => {
  assert.deepStrictEqual(pngSize(makePng(320, 640)), { width: 320, height: 640 });
  assert.strictEqual(pngSize(Buffer.from('no soy un png')), null);
});

test('ScreenStream no reenvia fotogramas identicos', async () => {
  const frame = makePng(8, 16, [1, 2, 3]);
  const stream = new ScreenStream('test', { capture: async () => frame });
  stream.setFps(30);

  const frames = [];
  stream.on('frame', (png) => frames.push(png));
  stream.subscribe();
  await new Promise((r) => setTimeout(r, 300));
  stream.stop();

  assert.strictEqual(frames.length, 1, 'pantalla estatica => un unico fotograma');
});

test('ScreenStream emite un fotograma por cada cambio real', async () => {
  let n = 0;
  const stream = new ScreenStream('test', { capture: async () => makePng(8, 16, [n++, 0, 0]) });
  stream.setFps(30);

  const frames = [];
  stream.on('frame', (png) => frames.push(png));
  stream.subscribe();
  await new Promise((r) => setTimeout(r, 300));
  stream.stop();

  assert.ok(frames.length >= 3, `se esperaban varios fotogramas, hubo ${frames.length}`);
});

test('ScreenStream avisa de resolucion y de dispositivo caido', async () => {
  let fail = true;
  const stream = new ScreenStream('test', {
    capture: async () => {
      if (fail) throw new Error('device offline');
      return makePng(100, 200);
    },
  });
  stream.setFps(30);

  const events = [];
  stream.on('offline', (m) => events.push(['offline', m]));
  stream.on('online', () => events.push(['online']));
  stream.on('resize', (s) => events.push(['resize', s]));
  stream.subscribe();

  await new Promise((r) => setTimeout(r, 150));
  fail = false;
  await new Promise((r) => setTimeout(r, 250));
  stream.stop();

  assert.deepStrictEqual(events[0], ['offline', 'device offline']);
  assert.ok(
    events.some((e) => e[0] === 'online'),
    'se notifica la recuperacion del dispositivo'
  );
  assert.deepStrictEqual(
    events.find((e) => e[0] === 'resize')[1],
    { width: 100, height: 200 }
  );
});

test('StreamHub comparte un unico bucle por serial', () => {
  const hub = new StreamHub((serial) => new ScreenStream(serial, { capture: async () => makePng(2, 2) }));
  const a = hub.get('127.0.0.1:4444');
  const b = hub.get('127.0.0.1:4444');
  assert.strictEqual(a, b, 'el mismo serial reutiliza el stream');
  assert.notStrictEqual(a, hub.get('emulator-5554'), 'seriales distintos, streams distintos');

  a.subscribe();
  a.subscribe();
  assert.strictEqual(a.subscribers, 2);
  assert.strictEqual(a.running, true);
  a.unsubscribe();
  assert.strictEqual(a.running, true, 'sigue vivo mientras quede un suscriptor');
  a.unsubscribe();
  assert.strictEqual(a.running, false, 'se apaga al soltar el ultimo suscriptor');
  hub.stopAll();
});
