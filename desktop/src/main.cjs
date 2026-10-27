'use strict';
const {app,BrowserWindow,Menu,shell,dialog,ipcMain,powerMonitor} = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const {createGateway,normalizeApi,DEFAULT_API} = require('./gateway.cjs');

let window, gateway, settings={}, settingsPath, closing=false, shuttingDown=false;
const dataArg=process.argv.find(x=>x.startsWith('--iot-profile='));
if(dataArg)app.setPath('userData',path.resolve(dataArg.slice(14)));
app.setAppUserModelId('com.zreyter.vehiculoiot');
if(!app.requestSingleInstanceLock())app.quit();
else {
  app.on('second-instance',()=>{if(window){if(window.isMinimized())window.restore();window.show();window.focus();}});
  app.whenReady().then(start).catch(error=>{dialog.showErrorBox('Vehículo IoT','No se pudo iniciar la aplicación.\n'+error.message);app.quit();});
}
function saveSettings() {
  fs.mkdirSync(path.dirname(settingsPath),{recursive:true});
  fs.writeFileSync(settingsPath+'.tmp',JSON.stringify(settings,null,2),'utf8');
  fs.renameSync(settingsPath+'.tmp',settingsPath);
}
async function suspendControls(message) {
  if(!window || window.isDestroyed())return;
  try {
    await window.webContents.executeJavaScript(`(async()=>{
      window.panelDrive?.suspend(${JSON.stringify(message)});
      const end=Date.now()+1200;
      while(window.RemoteDrive?.ending() && Date.now()<end)await new Promise(r=>setTimeout(r,25));
    })()`);
  }catch { /* El watchdog de la placa sigue funcionando si se cerró el documento. */ }
}
async function configureServer() {
  await suspendControls('Se cambió la conexión del servidor.');
  if(window && !window.isDestroyed())await window.loadURL(gateway.origin+'/desktop/');
}
async function start() {
  settingsPath=path.join(app.getPath('userData'),'configuracion.json');
  try {settings=JSON.parse(fs.readFileSync(settingsPath,'utf8'));}catch {settings={};}
  let apiUrl=DEFAULT_API;
  try {apiUrl=normalizeApi(settings.apiUrl || DEFAULT_API);}catch {}
  const apiArg=process.argv.find(x=>x.startsWith('--api-url='));
  if(apiArg)apiUrl=normalizeApi(apiArg.slice(10));
  gateway=await createGateway({apiUrl, assets:path.join(__dirname,'../assets'),onSave:async value=>{settings.apiUrl=value;saveSettings();}});
  const webSession=require('electron').session.defaultSession;
  webSession.setPermissionRequestHandler((contents,permission,callback)=>callback(false));
  webSession.setPermissionCheckHandler(()=>false);
  webSession.on('will-download',event=>event.preventDefault());
  ipcMain.on('controls:load',event=>{
    event.returnValue=event.sender===window?.webContents ? settings.controls || null : null;
  });
  ipcMain.on('controls:save',(event,value)=>{
    if(event.sender!==window?.webContents || !event.senderFrame.url.startsWith(gateway.origin+'/panel/') || typeof value!=='string' || value.length>32768)return;
    try {const parsed=JSON.parse(value);if(!parsed || typeof parsed!=='object' || Array.isArray(parsed))return;
      settings.controls=value;saveSettings();}catch {}
  });
  window=new BrowserWindow({width:1440,height:960,minWidth:820,minHeight:650,title:'Vehículo IoT',
    backgroundColor:'#f5f3e9',icon:path.join(__dirname,'../assets/icon.png'),show:false,
    webPreferences:{preload:path.join(__dirname,'preload.cjs'),nodeIntegration:false,contextIsolation:true,sandbox:true,webSecurity:true}});
  window.webContents.on('will-navigate',(event,url)=>{if(new URL(url).origin!==gateway.origin)event.preventDefault();});
  window.webContents.setWindowOpenHandler(({url})=>{
    try {const target=new URL(url);if(['http:','https:'].includes(target.protocol) && target.origin===gateway.apiUrl())shell.openExternal(target.href);}catch {}
    return {action:'deny'};
  });
  window.webContents.on('page-title-updated',event=>event.preventDefault());
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    {label:'Aplicación',submenu:[{label:'Cambiar servidor…',click:configureServer},{type:'separator'},
      {label:'Cerrar',accelerator:'Alt+F4',click:()=>window.close()}]},
    {label:'Edición',submenu:[{role:'undo',label:'Deshacer'},{role:'redo',label:'Rehacer'},{type:'separator'},
      {role:'cut',label:'Cortar'},{role:'copy',label:'Copiar'},{role:'paste',label:'Pegar'},{role:'selectAll',label:'Seleccionar todo'}]},
    {label:'Ver',submenu:[{label:'Recargar panel',accelerator:'Ctrl+R',click:async()=>{await suspendControls('Se recargó el panel.');window.reload();}},
      {role:'resetZoom',label:'Tamaño original'},{role:'zoomIn',label:'Acercar'},{role:'zoomOut',label:'Alejar'},{role:'togglefullscreen',label:'Pantalla completa'}]},
    {label:'Ayuda',submenu:[{label:'Cómo conectar',click:()=>dialog.showMessageBox(window,{type:'info',title:'Vehículo IoT',
      message:'Usa el mismo CONTROL_TOKEN de tu panel web.',detail:'Selecciona tu servidor, entra al panel y pulsa Conectar API. Para manejar el carro selecciona Conducción → ESP8266 por WiFi. En Termite envía WIFI. El mando se conecta a esta computadora. Cambia EC2 desde Aplicación → Cambiar servidor.'})},
      {label:'Acerca de…',click:()=>dialog.showMessageBox(window,{type:'info',title:'Vehículo IoT',message:'Vehículo IoT '+app.getVersion(),detail:'Aplicación de escritorio de Zreyter. API en EC2, MySQL en RDS y ESP8266 por WiFi/serial.'})}]}
  ]));
  window.on('blur',()=>{if(!closing)suspendControls('La aplicación perdió el foco.');});
  powerMonitor.on('suspend',()=>suspendControls('El equipo entró en suspensión.'));
  window.on('close',event=>{
    if(closing)return;
    event.preventDefault();closing=true;
    const timeout=new Promise(resolve=>setTimeout(resolve,1500));
    Promise.race([suspendControls('Se cerró la aplicación.'),timeout]).finally(()=>{if(!window.isDestroyed())window.destroy();});
  });
  window.once('ready-to-show',()=>{window.show();window.focus();});
  await window.loadURL(gateway.origin+'/desktop/');
}
app.on('before-quit',event=>{if(window && !window.isDestroyed() && !closing){event.preventDefault();window.close();}});
app.on('window-all-closed',async()=>{
  if(shuttingDown)return;
  shuttingDown=true;
  if(gateway)await gateway.close();
  app.quit();
});
