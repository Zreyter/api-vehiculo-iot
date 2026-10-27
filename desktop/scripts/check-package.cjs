'use strict';
const asar=require('@electron/asar');
const path=require('node:path');
const assert=require('node:assert/strict');
const file=path.resolve(__dirname,'../dist/win-unpacked/resources/app.asar');
const files=asar.listPackage(file);
for(const entry of files){
  assert.ok(!/(^|[\\/])(\.env|config_carro\.h|certs|\.venv|tests|node_modules)([\\/]|$)/.test(entry),entry);
}
assert.ok(files.some(entry=>entry.endsWith('remote-drive.js')));
assert.ok(files.some(entry=>entry.endsWith('preload.cjs')));
console.log('PASS contenido ASAR: panel y escritorio, sin configuración privada ni herramientas de desarrollo.');
