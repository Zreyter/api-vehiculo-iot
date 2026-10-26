'use strict';
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const source = process.env.IOT_PANEL_SOURCE || path.resolve(root, '../app/panel');
const target = path.join(root, 'assets/panel');
fs.mkdirSync(target, {recursive: true});
for (const asset of ['index.html','panel.css','panel.js','drive-controller.js','remote-drive.js','driving.js']) {
  fs.copyFileSync(path.join(source, asset), path.join(target, asset));
}
const driving=path.join(target,'driving.js');
const text=fs.readFileSync(driving,'utf8');
const save='localStorage.setItem(storageKey, JSON.stringify(preferences));';
if(!text.includes(save))throw new Error('Revisar la adaptación de preferencias: cambió el panel original.');
fs.writeFileSync(driving,text.replace(save,save+' window.iotDesktop?.saveControls(JSON.stringify(preferences));'));
console.log('Panel copiado: seis archivos públicos, sin configuración privada.');
