'use strict';
(async()=>{
  try {
    const config=await (await fetch('/desktop/config')).json();
    document.title='Vehículo IoT · Escritorio';
    document.querySelector('#apiEndpoint').textContent=config.apiUrl;
    const note=document.createElement('div');note.className='desktop-status';
    const label=document.createElement('span');label.textContent='APLICACIÓN DE ESCRITORIO · '+config.apiUrl;
    const change=document.createElement('a');change.href='/desktop/';change.textContent='Cambiar servidor ↗';
    change.addEventListener('click',()=>window.panelDrive?.suspend('Se cambió la conexión del servidor.'));
    note.append(label,change);document.querySelector('.main').prepend(note);
    const aws=document.querySelector('.aws p');if(aws)aws.textContent='Amazon EC2 + RDS MySQL · '+config.apiUrl;
    document.querySelectorAll('a[href="/docs"]').forEach(a=>a.href=config.apiUrl+'/docs');
    const architecture=document.querySelector('.architecture code');if(architecture)architecture.textContent=new URL(config.apiUrl).host;
    const footer=document.querySelector('.footer .flow span');if(footer)footer.textContent='Aplicación Windows';
  }catch {}
  let saved=localStorage.getItem('vehiculo-iot.conduccion.v1');
  function save(){try{const value=localStorage.getItem('vehiculo-iot.conduccion.v1');if(value && value!==saved){window.iotDesktop?.saveControls(value);saved=value;}}catch {}}
  setInterval(save,500);window.addEventListener('pagehide',save);
})();
