'use strict';
const {contextBridge,ipcRenderer} = require('electron');
try {
  const saved=ipcRenderer.sendSync('controls:load');
  if(saved)localStorage.setItem('vehiculo-iot.conduccion.v1',saved);
}catch {}
contextBridge.exposeInMainWorld('iotDesktop',Object.freeze({
  saveControls:value=>{if(typeof value==='string')ipcRenderer.send('controls:save',value);}
}));
