#!/usr/bin/env node
'use strict';

/**
 * `adb` simulado para las pruebas: acepta la misma linea de comandos que el
 * binario real y responde lo justo para ejercitar el middleware de punta a
 * punta sin un Android delante.
 *
 * Se controla por entorno:
 *   EVR_FAKE_ADB_LOG      fichero donde registrar cada invocacion (una por linea)
 *   EVR_FAKE_ADB_DEVICES  lista "serial:estado,serial:estado"; "none" = ninguno
 *   EVR_FAKE_ADB_PACKAGES paquetes instalados separados por comas
 *   EVR_FAKE_ADB_FAIL     si vale "screencap", screencap falla (guest apagado)
 */

const fs = require('fs');
const { makePng } = require('./png');

const argv = process.argv.slice(2);

if (process.env.EVR_FAKE_ADB_LOG) {
  fs.appendFileSync(process.env.EVR_FAKE_ADB_LOG, `${argv.join(' ')}\n`);
}

// Descarta "-s <serial>" para quedarse con el comando real.
const args = [...argv];
let serial = null;
if (args[0] === '-s') {
  args.shift();
  serial = args.shift();
}

const out = (text) => process.stdout.write(`${text}\n`);
const done = (code = 0) => process.exit(code);

const command = args[0];
const rest = args.slice(1);

switch (command) {
  case 'start-server':
  case 'kill-server':
    done();
    break;

  case 'devices': {
    const spec = process.env.EVR_FAKE_ADB_DEVICES ?? '127.0.0.1:4444:device';
    out('List of devices attached');
    if (spec !== 'none') {
      for (const entry of spec.split(',').filter(Boolean)) {
        const idx = entry.lastIndexOf(':');
        out(`${entry.slice(0, idx)}\t${entry.slice(idx + 1)}`);
      }
    }
    out('');
    done();
    break;
  }

  case 'connect':
    out(`connected to ${rest[0]}`);
    done();
    break;

  case 'disconnect':
    out(rest[0] ? `disconnected ${rest[0]}` : 'disconnected everything');
    done();
    break;

  case 'wait-for-device':
    done();
    break;

  case 'root':
  case 'remount':
    out('restarting adbd as root');
    done();
    break;

  case 'reboot':
    done();
    break;

  case 'install':
    out('Success');
    done();
    break;

  case 'uninstall':
    out('Success');
    done();
    break;

  case 'pull':
    fs.writeFileSync(rest[1], 'ro.product.model=EVR Test\nro.build.version.release=13\n');
    out('1 file pulled');
    done();
    break;

  case 'push':
    out('1 file pushed');
    done();
    break;

  case 'exec-out': {
    if (process.env.EVR_FAKE_ADB_FAIL === 'screencap') {
      process.stderr.write('error: device offline\n');
      done(1);
    }
    // Color pseudo-aleatorio: cada captura es un fotograma distinto.
    const rnd = () => 40 + Math.floor(Math.random() * 200);
    const w = parseInt(process.env.EVR_FAKE_ADB_W || '270', 10);
    const h = parseInt(process.env.EVR_FAKE_ADB_H || '480', 10);
    process.stdout.write(makePng(w, h, [rnd(), rnd(), rnd()]));
    done();
    break;
  }

  case 'shell': {
    const cmd = rest.join(' ');
    if (/^wm size/.test(cmd)) out('Physical size: 1080x1920');
    else if (/getprop/.test(cmd)) out('EVR Test\n13\nevr');
    else if (/^pm list packages/.test(cmd)) {
      const wanted = cmd.split(/\s+/).pop();
      const installed = (process.env.EVR_FAKE_ADB_PACKAGES || 'com.zhiliaoapp.musically').split(',');
      for (const pkg of installed) if (pkg.includes(wanted)) out(`package:${pkg}`);
    } else if (/^monkey /.test(cmd)) {
      const pkg = (cmd.match(/-p\s+(\S+)/) || [])[1];
      const installed = (process.env.EVR_FAKE_ADB_PACKAGES || 'com.zhiliaoapp.musically').split(',');
      if (installed.includes(pkg)) out('Events injected: 1');
      else out(`** No activities found to run, monkey aborted.`);
    } else if (/^input /.test(cmd)) {
      // sin salida, como el adb real
    } else if (/^am start/.test(cmd)) {
      out('Starting: Intent { act=android.intent.action.VIEW }');
    }
    done();
    break;
  }

  case 'version':
    out('Android Debug Bridge version 1.0.41 (fake)');
    done();
    break;

  default:
    process.stderr.write(`fake-adb: comando no soportado: ${command}\n`);
    done(1);
}
