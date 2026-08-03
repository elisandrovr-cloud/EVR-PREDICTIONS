'use strict';

const { EventEmitter } = require('events');
const crypto = require('crypto');
const adb = require('./adb-service');
const config = require('./config');
const log = require('./logger');

/**
 * Fuente de fotogramas del guest (Fase 3).
 *
 * Un unico bucle de captura por serial, compartido entre todos los clientes
 * suscritos: capturar la pantalla es caro (un proceso adb por fotograma), asi
 * que N consolas abiertas no deben multiplicar el coste.
 *
 * El bucle es auto-regulado: el siguiente fotograma se pide cuando termina el
 * anterior, nunca en paralelo. Si el guest tarda mas que el intervalo objetivo,
 * el stream baja de fps solo en lugar de encolar capturas.
 *
 * Los fotogramas identicos al anterior no se reenvian (pantalla estatica =
 * ancho de banda ~0); el hash md5 del PNG basta para detectarlo.
 */

/** Lee ancho/alto de la cabecera IHDR de un PNG. */
function pngSize(buf) {
  if (!buf || buf.length < 24 || buf.readUInt32BE(0) !== 0x89504e47) return null;
  return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
}

class ScreenStream extends EventEmitter {
  /**
   * @param {string} serial serial/endpoint ADB del guest
   * @param {object} [deps] inyeccion para pruebas ({ capture })
   */
  constructor(serial, { capture } = {}) {
    super();
    this.serial = serial;
    this.capture = capture || ((s) => adb.screencap(s));
    this.subscribers = 0;
    this.running = false;
    this.timer = null;
    this.lastHash = null;
    this.lastSize = null;
    this.lastError = null;
    this.frames = 0;
    this.intervalMs = Math.round(1000 / config.streamFps);
  }

  setFps(fps) {
    const clamped = Math.min(30, Math.max(1, Number(fps) || config.streamFps));
    this.intervalMs = Math.round(1000 / clamped);
    return clamped;
  }

  get fps() {
    return Math.round(1000 / this.intervalMs);
  }

  subscribe() {
    this.subscribers += 1;
    if (!this.running) this.start();
    return () => this.unsubscribe();
  }

  unsubscribe() {
    this.subscribers = Math.max(0, this.subscribers - 1);
    if (this.subscribers === 0) this.stop();
  }

  start() {
    if (this.running) return;
    this.running = true;
    this.lastHash = null; // fuerza un fotograma completo al primer suscriptor
    log.debug(`stream ${this.serial}: iniciado (${this.fps} fps)`);
    this._loop();
  }

  stop() {
    this.running = false;
    clearTimeout(this.timer);
    this.timer = null;
    log.debug(`stream ${this.serial}: detenido`);
  }

  async _loop() {
    if (!this.running) return;
    const started = Date.now();
    try {
      const png = await this.capture(this.serial);
      const hash = crypto.createHash('md5').update(png).digest('hex');
      if (this.lastError) {
        this.lastError = null;
        this.emit('online');
      }
      if (hash !== this.lastHash) {
        this.lastHash = hash;
        this.frames += 1;
        const size = pngSize(png);
        if (size && (!this.lastSize || size.width !== this.lastSize.width || size.height !== this.lastSize.height)) {
          this.lastSize = size;
          this.emit('resize', size);
        }
        this.emit('frame', png, this.lastSize);
      }
    } catch (err) {
      if (this.lastError !== err.message) {
        this.lastError = err.message;
        this.emit('offline', err.message);
      }
    }
    if (!this.running) return;
    // Ritmo auto-regulado: descuenta lo que costo la captura.
    const wait = Math.max(50, this.intervalMs - (Date.now() - started));
    this.timer = setTimeout(() => this._loop(), wait);
    this.timer.unref();
  }
}

/** Registro de streams por serial, con conteo de referencias. */
class StreamHub {
  constructor(factory) {
    this.streams = new Map();
    this.factory = factory || ((serial) => new ScreenStream(serial));
  }

  get(serial) {
    const key = serial || config.defaultSerial;
    if (!this.streams.has(key)) this.streams.set(key, this.factory(key));
    return this.streams.get(key);
  }

  release(serial) {
    const key = serial || config.defaultSerial;
    const stream = this.streams.get(key);
    if (stream && stream.subscribers === 0) {
      stream.stop();
      this.streams.delete(key);
    }
  }

  stopAll() {
    for (const stream of this.streams.values()) stream.stop();
    this.streams.clear();
  }
}

module.exports = { ScreenStream, StreamHub, pngSize };
