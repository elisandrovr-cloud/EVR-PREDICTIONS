'use strict';

const config = require('./config');

const LEVELS = { error: 0, warn: 1, info: 2, debug: 3 };
const threshold = LEVELS[config.logLevel] !== undefined ? LEVELS[config.logLevel] : LEVELS.info;

function ts() {
  return new Date().toISOString();
}

function make(level, stream) {
  return (...args) => {
    if (LEVELS[level] > threshold) return;
    stream(`[${ts()}] [${level.toUpperCase()}]`, ...args);
  };
}

module.exports = {
  error: make('error', console.error),
  warn: make('warn', console.warn),
  info: make('info', console.log),
  debug: make('debug', console.log),
};
